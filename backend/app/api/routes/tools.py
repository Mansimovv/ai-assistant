import time

from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError

from app.ai.router import ActionRecord
from app.api.deps import ConversationsDep, DeviceActionsDep, RegistryDep
from app.devices.capabilities import CAPABILITIES
from app.schemas.tools import ToolExecuteRequest, ToolExecuteResponse, ToolInfo
from app.tools.registry import ConfirmationRequiredError, ToolNotFoundError

router = APIRouter(tags=["tools"])


@router.get("/tools")
async def list_tools(registry: RegistryDep, devices: DeviceActionsDep) -> list[ToolInfo]:
    """Local tools plus the capabilities of every online device."""
    local = [
        ToolInfo(
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters.model_json_schema(),
            permission=tool.permission,
            requires_confirmation=tool.requires_confirmation,
            risk="low",
            target="backend",
        )
        for tool in registry.list_tools()
    ]
    remote = [
        ToolInfo(
            name=spec.name,
            description=spec.description,
            parameters=spec.parameters,
            risk=devices.risk(spec.name),
            target="device",
        )
        for spec in devices.specs()
    ]
    return local + remote


@router.post("/tools/{name}/execute")
async def execute_tool(
    name: str,
    request: ToolExecuteRequest,
    registry: RegistryDep,
    devices: DeviceActionsDep,
    conversations: ConversationsDep,
) -> ToolExecuteResponse:
    """Run a tool directly. Useful for testing a device without going through the model."""
    if devices.knows(name):
        started = time.monotonic()
        result = await devices.execute(name, request.arguments)
        await conversations.log_action(
            ActionRecord(
                tool=name,
                arguments=request.arguments,
                ok=result.ok,
                error=result.error,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        )
        return ToolExecuteResponse(tool=name, result=result.model_dump(exclude_none=True))

    if name in {f"{device_type}_{capability}" for device_type in ("mac", "iphone") for capability in CAPABILITIES}:
        raise HTTPException(status.HTTP_409_CONFLICT, f"No online device provides {name}")

    try:
        result = await registry.execute(name, request.arguments, confirmed=request.confirmed)
    except ToolNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown tool: {name}") from exc
    except ConfirmationRequiredError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Tool {name!r} requires confirmation") from exc
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, exc.errors(include_url=False, include_context=False)
        ) from exc
    return ToolExecuteResponse(tool=name, result={"ok": True, "data": result})
