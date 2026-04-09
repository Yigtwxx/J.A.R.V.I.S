from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.middleware.security import verify_api_key
from app.services.self_healing_service import self_healing_service
from app.services.system_service import system_service
from app.utils.logger import logger

router = APIRouter(prefix="/api/system", tags=["system"])


class CommandRequest(BaseModel):
    command: str
    timeout: int = 30


class AppRequest(BaseModel):
    app_name: str


class UrlRequest(BaseModel):
    url: str


class ActionApproval(BaseModel):
    action_id: str


@router.post("/execute/command")
async def request_command(request: CommandRequest, _api_key: str = Depends(verify_api_key)):
    """Request to execute a shell command (requires approval)."""
    try:
        action = system_service.request_action(
            action_type="run_command",
            description=f"Run command: {request.command}",
            parameters={"command": request.command, "timeout": request.timeout},
        )
        return {
            "status": "pending_approval",
            "action_id": action.action_id,
            "description": action.description,
            "message": "This action requires user approval before execution.",
        }
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/execute/app")
async def request_open_app(request: AppRequest, _api_key: str = Depends(verify_api_key)):
    """Request to open an application (requires approval)."""
    try:
        action = system_service.request_action(
            action_type="open_app",
            description=f"Open application: {request.app_name}",
            parameters={"app_name": request.app_name},
        )
        return {
            "status": "pending_approval",
            "action_id": action.action_id,
            "description": action.description,
        }
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/execute/url")
async def request_open_url(request: UrlRequest, _api_key: str = Depends(verify_api_key)):
    """Request to open a URL in browser (requires approval)."""
    try:
        action = system_service.request_action(
            action_type="open_url",
            description=f"Open URL: {request.url}",
            parameters={"url": request.url},
        )
        return {
            "status": "pending_approval",
            "action_id": action.action_id,
            "description": action.description,
        }
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/approve")
async def approve_action(request: ActionApproval, _api_key: str = Depends(verify_api_key)):
    """Approve a pending action for execution."""
    try:
        action = system_service.approve_action(request.action_id)
        return {
            "status": action.status.value,
            "result": action.result,
            "action_id": action.action_id,
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="Action not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/deny")
async def deny_action(request: ActionApproval, _api_key: str = Depends(verify_api_key)):
    """Deny a pending action."""
    try:
        action = system_service.deny_action(request.action_id)
        return {"status": "denied", "action_id": action.action_id}
    except KeyError:
        raise HTTPException(status_code=404, detail="Action not found")


@router.get("/pending")
async def list_pending(_api_key: str = Depends(verify_api_key)):
    """List all pending actions awaiting approval."""
    return {"pending_actions": system_service.list_pending()}


@router.get("/history")
async def action_history(limit: int = 50, _api_key: str = Depends(verify_api_key)):
    """Get history of executed/denied actions."""
    return {"history": system_service.get_history(limit)}


# ─── Self-Healing / Service Status ─────────────────────────

@router.get("/service-status")
async def service_status(_api_key: str = Depends(verify_api_key)):
    """Get current status of all monitored services."""
    return self_healing_service.get_status()


@router.get("/health-log")
async def health_log(limit: int = 50, _api_key: str = Depends(verify_api_key)):
    """Get self-healing activity log."""
    return {"log": self_healing_service.get_health_log(limit)}
