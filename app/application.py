from fastapi import FastAPI

from app.api.events import create_events_router
from app.api.device import (
    DeviceAuthenticationService,
    DeviceRegistrationService,
    create_device_router,
)
from app.api.message import MessageCreationService, create_message_router
from app.api.message_pull import MessagePullingService, create_message_pull_router
from app.api.message_status import MessageStateUpdatingService, create_message_status_router
from app.api.inbox import InboundCreatingService, create_inbox_router
from app.config import Settings
from app.database import Database
from app.errors import install_error_handling
from app.services.device_auth_service import DeviceAuthService
from app.services.device_service import DeviceService
from app.services.message_publisher import (
    MessageEnqueuedPublisher,
    RegistryMessageEnqueuedPublisher,
)
from app.services.message_service import MessageCommandService
from app.services.message_pull_service import MessagePullService
from app.services.message_state_service import MessageStateService
from app.services.inbound_message_service import InboundMessageService
from app.services.inbound_publisher import InboundMessagePublisher, NoOpInboundMessagePublisher
from app.services.sse import SseConnectionRegistry
from pg.admin_ui import mount_admin_ui


def create_app(
    settings: Settings,
    device_service: DeviceRegistrationService | None = None,
    device_auth_service: DeviceAuthenticationService | None = None,
    message_service: MessageCreationService | None = None,
    message_publisher: MessageEnqueuedPublisher | None = None,
    sse_registry: SseConnectionRegistry | None = None,
    message_pull_service: MessagePullingService | None = None,
    message_state_service: MessageStateUpdatingService | None = None,
    inbound_message_service: InboundCreatingService | None = None,
    inbound_publisher: InboundMessagePublisher | None = None,
) -> FastAPI:
    app = FastAPI(title="Virgo SMS Gateway")
    install_error_handling(app)
    database = Database(settings.database_url)
    service = (
        device_service
        if device_service is not None
        else DeviceService(database)
    )
    auth_service = (
        device_auth_service
        if device_auth_service is not None
        else DeviceAuthService(database)
    )
    registry = (
        sse_registry
        if sse_registry is not None
        else SseConnectionRegistry()
    )
    publisher = (
        message_publisher
        if message_publisher is not None
        else RegistryMessageEnqueuedPublisher(registry)
    )
    business_message_service = message_service or MessageCommandService(
        database,
        online_window_seconds=settings.device_online_window_seconds,
        publisher=publisher,
    )
    pull_service = message_pull_service or MessagePullService(database)
    state_service = message_state_service or MessageStateService(database)
    inbound_service = inbound_message_service or InboundMessageService(
        database, inbound_publisher or NoOpInboundMessagePublisher()
    )
    app.include_router(
        create_device_router(
            settings.private_registration_token,
            service,
            auth_service,
        )
    )
    app.include_router(
        create_message_router(
            settings.business_api_token,
            business_message_service,
        )
    )
    app.include_router(create_events_router(auth_service, registry))
    app.include_router(create_message_pull_router(auth_service, pull_service))
    app.include_router(create_message_status_router(auth_service, state_service))
    app.include_router(create_inbox_router(auth_service, inbound_service))
    mount_admin_ui(app, database)
    return app
