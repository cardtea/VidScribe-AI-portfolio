# Example Usage of Hybrid Monitor in main.py

"""
This example demonstrates how to use the new hybrid monitoring system
in your NiceGUI application.
"""

from core.monitor import Monitor
from nicegui import ui

# Initialize the monitor (do this once at startup)
monitor = Monitor()

# In your NiceGUI UI setup:
with ui.column().classes('w-64 bg-gray-800 q-pa-md'):
    ui.label('System Resources').classes('text-h6 text-green-400 q-mb-md')
    
    # CPU Monitoring
    ui.label('CPU').classes('text-sm text-gray-400 q-mt-sm')
    sys_cpu_label = ui.label('System: 0%').classes('text-md')
    app_cpu_label = ui.label('App: 0%').classes('text-md text-cyan-300')
    
    # RAM Monitoring
    ui.label('RAM').classes('text-sm text-gray-400 q-mt-sm')
    sys_ram_label = ui.label('System: 0%').classes('text-md')
    sys_ram_detail = ui.label('0GB / 0GB').classes('text-sm text-gray-500')
    app_ram_label = ui.label('App: 0GB').classes('text-md text-cyan-300')
    
    # GPU Monitoring
    ui.label('GPU').classes('text-sm text-gray-400 q-mt-sm')
    gpu_name_label = ui.label('N/A').classes('text-xs text-gray-500')
    gpu_load_label = ui.label('Load: 0%').classes('text-md')
    
    # VRAM Monitoring
    ui.label('VRAM').classes('text-sm text-gray-400 q-mt-sm')
    vram_label = ui.label('0GB / 0GB').classes('text-md')

# Update function (called by timer)
def update_stats():
    """Update all resource labels with current stats"""
    stats = monitor.get_stats()
    
    # Update CPU labels
    sys_cpu_label.set_text(f"System: {stats['sys_cpu']:.1f}%")
    app_cpu_label.set_text(f"App: {stats['app_cpu']:.1f}%")
    
    # Update RAM labels
    sys_ram_label.set_text(f"System: {stats['sys_ram_percent']:.1f}%")
    sys_ram_detail.set_text(f"{stats['sys_ram_used_gb']:.1f}GB / {stats['sys_ram_total_gb']:.1f}GB")
    app_ram_label.set_text(f"App: {stats['app_ram_gb']:.2f}GB")
    
    # Update GPU labels
    gpu_name_label.set_text(f"{stats['gpu_name']}")
    gpu_load_label.set_text(f"Load: {stats['gpu_load']:.1f}%")
    
    # Update VRAM labels
    vram_label.set_text(f"{stats['vram_used']:.1f}GB / {stats['vram_total']:.1f}GB")

# Set up timer to update every second
ui.timer(1.0, update_stats)

# Alternative: Manual stats retrieval
def check_resources_manually():
    """Example of getting stats without UI binding"""
    stats = monitor.get_stats()
    
    print(f"System CPU: {stats['sys_cpu']}%")
    print(f"App CPU: {stats['app_cpu']}%")
    print(f"System RAM: {stats['sys_ram_used_gb']:.1f}GB / {stats['sys_ram_total_gb']:.1f}GB")
    print(f"App RAM: {stats['app_ram_gb']:.2f}GB")
    print(f"GPU: {stats['gpu_name']} @ {stats['gpu_load']}%")
    print(f"VRAM: {stats['vram_used']:.1f}GB / {stats['vram_total']:.1f}GB")
    
    return stats

# Advanced: Progress bars for CPU (optional)
with ui.column():
    ui.label('CPU Usage')
    
    # System CPU progress bar
    sys_cpu_progress = ui.linear_progress(value=0).props('color=orange')
    sys_cpu_text = ui.label('System: 0%')
    
    # App CPU progress bar
    app_cpu_progress = ui.linear_progress(value=0).props('color=cyan')
    app_cpu_text = ui.label('App: 0%')
    
    def update_cpu_bars():
        stats = monitor.get_stats()
        
        # Update progress bars (value 0-1)
        sys_cpu_progress.set_value(stats['sys_cpu'] / 100.0)
        app_cpu_progress.set_value(stats['app_cpu'] / 100.0)
        
        # Update text labels
        sys_cpu_text.set_text(f"System: {stats['sys_cpu']:.1f}%")
        app_cpu_text.set_text(f"App: {stats['app_cpu']:.1f}%")
    
    ui.timer(1.0, update_cpu_bars)
