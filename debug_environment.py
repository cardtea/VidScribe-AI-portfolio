
import sys
import os

print(f"Python Executable: {sys.executable}")
print(f"Python Version: {sys.version}")

print("-" * 20)
print("Checking pynvml...")
try:
    import pynvml
    print(f"pynvml imported successfully: {pynvml}")
    try:
        pynvml.nvmlInit()
        print(f"Driver Version: {pynvml.nvmlSystemGetDriverVersion()}")
        device_count = pynvml.nvmlDeviceGetCount()
        print(f"Device Count: {device_count}")
        for i in range(device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            print(f"Device {i}: {pynvml.nvmlDeviceGetName(handle)}")
        pynvml.nvmlShutdown()
    except Exception as e:
        print(f"pynvml init failed: {e}")
except ImportError as e:
    print(f"pynvml import failed: {e}")

print("-" * 20)
print("Checking torch...")
try:
    import torch
    print(f"Torch Version: {torch.__version__}")
    print(f"CUDA Available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA Device: {torch.cuda.get_device_name(0)}")
        print(f"CUDA Version: {torch.version.cuda}")
    else:
        print("CUDA is NOT available.")
except ImportError as e:
    print(f"Torch import failed: {e}")
