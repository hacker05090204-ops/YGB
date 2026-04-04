"""Test the fixed AutoTrainer _gpu_train_step."""
import sys, os, traceback
sys.path.insert(0, r'c:\Users\KINETIC04\Pictures\YGB')
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')

print("=== Testing Fixed AutoTrainer ===", flush=True)
try:
    from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
    trainer = AutoTrainer()
    print(f"Created, state={trainer.state}", flush=True)
    
    result = trainer._init_gpu_resources()
    print(f"Init result: {result}", flush=True)
    print(f"GPU initialized: {trainer._gpu_initialized}", flush=True)
    
    if result:
        success, accuracy, loss = trainer._gpu_train_step()
        print(f"Train step: success={success}, accuracy={accuracy:.4f}, loss={loss:.4f}", flush=True)
    else:
        print("GPU init failed!", flush=True)
except Exception as e:
    print(f"ERROR: {e}", flush=True)
    traceback.print_exc()
