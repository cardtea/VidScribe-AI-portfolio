"""
Hybrid Resource Monitoring Module
Monitors both System-wide and Process-specific resources
"""
import psutil
import logging
import subprocess
import os

logger = logging.getLogger(__name__)

# Try to import pynvml for GPU monitoring
try:
    import pynvml
    NVML_AVAILABLE = True
    try:
        pynvml.nvmlInit()
        # Get GPU info for diagnostics
        device_count = pynvml.nvmlDeviceGetCount()
        logger.info(f"✅ NVML initialized successfully. Found {device_count} GPU(s)")
        
        for i in range(device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            logger.info(f"  GPU {i}: {name}")
            
    except Exception as e:
        NVML_AVAILABLE = False
        logger.warning(f"⚠️ NVML initialization failed: {e}")
        logger.info("Falling back to nvidia-smi for GPU monitoring...")
except ImportError as e:
    NVML_AVAILABLE = False
    logger.warning(f"⚠️ pynvml not available: {e}")
    logger.info("Will attempt to use nvidia-smi for GPU monitoring...")


def get_gpu_info_from_smi():
    """Fallback method using nvidia-smi command"""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total,name', '--format=csv,noheader,nounits'],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            # Parse output: "gpu_util, mem_used, mem_total, name"
            values = result.stdout.strip().split(',')
            if len(values) >= 3:
                gpu_percent = float(values[0].strip())
                vram_used_mb = float(values[1].strip())
                vram_total_mb = float(values[2].strip())
                vram_used_gb = round(vram_used_mb / 1024, 2)
                vram_total_gb = round(vram_total_mb / 1024, 2)
                gpu_name = values[3].strip() if len(values) > 3 else "Unknown GPU"
                return {
                    'gpu_load': gpu_percent,
                    'vram_used': vram_used_gb,
                    'vram_total': vram_total_gb,
                    'gpu_name': gpu_name
                }
    except Exception as e:
        logger.debug(f"nvidia-smi fallback failed: {e}")
    
    return None


class Monitor:
    def __init__(self):
        """Initialize monitor with current process"""
        self.pid = os.getpid()
        try:
            self.process = psutil.Process(self.pid)
            logger.info(f"Monitor initialized for PID {self.pid}")
        except psutil.NoSuchProcess:
            logger.error(f"Failed to initialize monitor for PID {self.pid}")
            self.process = None
    
    def get_process_resources(self):
        """
        Get resources used by this process and all its children (recursive)
        Returns: (cpu_percent, ram_gb)
        """
        if not self.process:
            return 0.0, 0.0
        
        try:
            # Get main process stats
            # cpu_percent() returns total across all cores, need to normalize
            cpu_total = self.process.cpu_percent(interval=0.1)
            ram_total = self.process.memory_info().rss / (1024 ** 3)  # Convert to GB
            
            # Get all children recursively
            try:
                children = self.process.children(recursive=True)
                for child in children:
                    try:
                        cpu_total += child.cpu_percent(interval=0.1)
                        ram_total += child.memory_info().rss / (1024 ** 3)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        # Child process may have terminated
                        continue
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # Main process may have issues accessing children
                pass
            
            # Normalize CPU to 0-100% (psutil returns total across all cores)
            # For example, on 8-core CPU, 800% means 100% usage
            cpu_count = psutil.cpu_count()
            cpu_normalized = cpu_total / cpu_count if cpu_count else cpu_total
            
            return round(cpu_normalized, 1), round(ram_total, 2)
            
        except psutil.NoSuchProcess:
            logger.warning(f"Process {self.pid} no longer exists")
            return 0.0, 0.0
        except Exception as e:
            logger.error(f"Error getting process resources: {e}")
            return 0.0, 0.0
    
    def get_system_resources(self):
        """
        Get system-wide resources
        Returns: (cpu_percent, ram_percent, ram_used_gb, ram_total_gb)
        """
        try:
            # System CPU
            sys_cpu = psutil.cpu_percent(interval=0.1)
            
            # System RAM
            ram = psutil.virtual_memory()
            sys_ram_percent = ram.percent
            sys_ram_used_gb = round(ram.used / (1024 ** 3), 2)
            sys_ram_total_gb = round(ram.total / (1024 ** 3), 2)
            
            return sys_cpu, sys_ram_percent, sys_ram_used_gb, sys_ram_total_gb
            
        except Exception as e:
            logger.error(f"Error getting system resources: {e}")
            return 0.0, 0.0, 0.0, 0.0
    
    def get_gpu_resources(self):
        """
        Get GPU and VRAM usage
        Returns: (gpu_load, vram_used_gb, vram_total_gb, gpu_name)
        """
        gpu_load = 0.0
        vram_used = 0.0
        vram_total = 0.0
        gpu_name = "N/A"
        
        if NVML_AVAILABLE:
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)  # Get first GPU
                
                # GPU Name
                gpu_name = pynvml.nvmlDeviceGetName(handle)
                
                # GPU Utilization
                utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
                gpu_load = float(utilization.gpu)
                
                # VRAM Usage
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                vram_used = round(mem_info.used / (1024 ** 3), 2)
                vram_total = round(mem_info.total / (1024 ** 3), 2)
                
            except Exception as e:
                logger.debug(f"NVML GPU monitoring error: {e}")
        else:
            # Fallback to nvidia-smi
            smi_data = get_gpu_info_from_smi()
            if smi_data:
                gpu_load = smi_data['gpu_load']
                vram_used = smi_data['vram_used']
                vram_total = smi_data['vram_total']
                gpu_name = smi_data['gpu_name']
        
        return gpu_load, vram_used, vram_total, gpu_name
    
    def get_stats(self):
        """
        Get comprehensive system and process statistics
        
        Returns:
            dict: {
                "sys_cpu": float,           # System-wide CPU %
                "app_cpu": float,           # App + children CPU %
                "sys_ram_percent": float,   # System RAM %
                "sys_ram_used_gb": float,   # System RAM used (GB)
                "sys_ram_total_gb": float,  # System RAM total (GB)
                "app_ram_gb": float,        # App + children RAM (GB)
                "gpu_load": float,          # GPU utilization %
                "vram_used": float,         # VRAM used (GB)
                "vram_total": float,        # VRAM total (GB)
                "gpu_name": str             # GPU name
            }
        """
        try:
            # Get process-specific resources
            app_cpu, app_ram = self.get_process_resources()
            
            # Get system-wide resources
            sys_cpu, sys_ram_percent, sys_ram_used_gb, sys_ram_total_gb = self.get_system_resources()
            
            # Get GPU resources
            gpu_load, vram_used, vram_total, gpu_name = self.get_gpu_resources()
            
            return {
                "sys_cpu": sys_cpu,
                "app_cpu": app_cpu,
                "sys_ram_percent": sys_ram_percent,
                "sys_ram_used_gb": sys_ram_used_gb,
                "sys_ram_total_gb": sys_ram_total_gb,
                "app_ram_gb": app_ram,
                "gpu_load": gpu_load,
                "vram_used": vram_used,
                "vram_total": vram_total,
                "gpu_name": gpu_name
            }
            
        except Exception as e:
            logger.error(f"Error in get_stats: {e}")
            # Return safe defaults
            return {
                "sys_cpu": 0.0,
                "app_cpu": 0.0,
                "sys_ram_percent": 0.0,
                "sys_ram_used_gb": 0.0,
                "sys_ram_total_gb": 0.0,
                "app_ram_gb": 0.0,
                "gpu_load": 0.0,
                "vram_used": 0.0,
                "vram_total": 0.0,
                "gpu_name": "N/A"
            }
