from fastapi import APIRouter, HTTPException

from app.plugins import plugin_manager

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


@router.get("/")
async def list_plugins():
    """List all discovered plugins with their enabled/disabled state."""
    return {"plugins": plugin_manager.list_plugins()}


@router.post("/{name}/toggle")
async def toggle_plugin(name: str):
    """Toggle a plugin's enabled state."""
    try:
        new_state = plugin_manager.toggle(name)
        return {"name": name, "enabled": new_state}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")


@router.post("/{name}/run")
async def run_plugin(name: str, query: str):
    """Manually run a specific plugin."""
    result = await plugin_manager.run_plugin(name, query)
    if "error" in result and not result.get("results"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result
