"""
Follow-Through Tracer

Structured step-by-step execution tracing for visibility into data flow.
Provides clear, human-readable logs showing how data moves through the system.
"""
import functools
import logging
from typing import Any, Callable, Optional
from datetime import datetime

from .config import settings

# Create a dedicated logger for follow-through tracing
tracer = logging.getLogger("followthrough")


def _preview(data: Any, max_len: int = 50) -> str:
    """Create a short preview of data."""
    if data is None:
        return "<None>"
    text = str(data)
    if len(text) > max_len:
        return f"{text[:max_len]}..."
    return text


def _format_step(icon: str, step: str, module: str, detail: str = "") -> str:
    """Format a trace step with consistent styling."""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    base = f"[{timestamp}] {icon} [{module}] {step}"
    if detail:
        return f"{base}: {detail}"
    return base


def trace_input(module: str, input_name: str, value: Any):
    """Log an input value entering a module."""
    if not settings.follow_through:
        return
    preview = _preview(value)
    tracer.info(_format_step("→", f"INPUT {input_name}", module, preview))


def trace_parse(module: str, description: str, parsed_value: Any = None):
    """Log how input was parsed/interpreted."""
    if not settings.follow_through:
        return
    msg = description
    if parsed_value is not None:
        msg += f" => {_preview(parsed_value)}"
    tracer.info(_format_step("⚙", "PARSED", module, msg))


def trace_call(module: str, function: str, args_preview: str = ""):
    """Log that a function is being called."""
    if not settings.follow_through:
        return
    detail = f"calling {function}()"
    if args_preview:
        detail += f" with {args_preview}"
    tracer.info(_format_step("▶", "CALL", module, detail))


def trace_result(module: str, function: str, success: bool, result_preview: Any = None):
    """Log the result of a function call."""
    if not settings.follow_through:
        return
    status = "✓ SUCCESS" if success else "✗ FAILED"
    detail = f"{function}() {status}"
    if result_preview is not None:
        detail += f" => {_preview(result_preview)}"
    tracer.info(_format_step("◀", "RESULT", module, detail))


def trace_pass(from_module: str, to_module: str, data_name: str, data: Any = None):
    """Log data being passed between modules."""
    if not settings.follow_through:
        return
    detail = f"passing {data_name} to {to_module}"
    if data is not None:
        detail += f" ({_preview(data, 30)})"
    tracer.info(_format_step("↪", "PASS", from_module, detail))


def trace_step(module: str, description: str):
    """Log a general step in processing."""
    if not settings.follow_through:
        return
    tracer.info(_format_step("•", "STEP", module, description))


def trace_output(module: str, output_name: str, value: Any):
    """Log an output value leaving a module."""
    if not settings.follow_through:
        return
    preview = _preview(value)
    tracer.info(_format_step("←", f"OUTPUT {output_name}", module, preview))


def trace_section(title: str):
    """Log a section divider for major pipeline stages."""
    if not settings.follow_through:
        return
    bar = "─" * 40
    tracer.info(f"\n{bar}")
    tracer.info(f"  {title.upper()}")
    tracer.info(f"{bar}")


def traced(module: str):
    """
    Decorator to automatically trace function entry/exit.
    
    Usage:
        @traced("engine.reasoning")
        async def generate_response(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not settings.follow_through:
                return await func(*args, **kwargs)
            
            func_name = func.__name__
            trace_call(module, func_name)
            
            try:
                result = await func(*args, **kwargs)
                trace_result(module, func_name, True, result)
                return result
            except Exception as e:
                trace_result(module, func_name, False, str(e))
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not settings.follow_through:
                return func(*args, **kwargs)
            
            func_name = func.__name__
            trace_call(module, func_name)
            
            try:
                result = func(*args, **kwargs)
                trace_result(module, func_name, True, result)
                return result
            except Exception as e:
                trace_result(module, func_name, False, str(e))
                raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def setup_follow_through_logging():
    """Configure the follow-through logger."""
    if settings.follow_through:
        # Create handler with custom format
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        
        tracer.addHandler(handler)
        tracer.setLevel(logging.INFO)
        tracer.propagate = False  # Don't propagate to root logger
        
        tracer.info("\n" + "=" * 50)
        tracer.info("  FOLLOW-THROUGH MODE ENABLED")
        tracer.info("  Tracing execution flow...")
        tracer.info("=" * 50 + "\n")
