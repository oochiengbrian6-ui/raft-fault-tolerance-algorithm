"""System Runner - Starts all components"""
import subprocess
import time
import sys

class SystemRunner:
    def __init__(self):
        self.processes = []
    
    def start_coordinator(self):
        print("Starting Coordinator...")
        proc = subprocess.Popen([sys.executable, 'coordinator.py'])
        self.processes.append(proc)
        time.sleep(2)
    
    def start_participant(self, node_id, port, failure_rate=0.0):
        print(f"Starting Participant {node_id} on port {port}...")
        proc = subprocess.Popen([sys.executable, 'participant.py', str(node_id), str(port), str(failure_rate)])
        self.processes.append(proc)
        time.sleep(1)
    
    def run_client(self):
        print("\nRunning Client Tests...")
        time.sleep(1)
        subprocess.run([sys.executable, 'client.py'])
    
    def stop_all(self):
        print("\nStopping all processes...")
        for proc in self.processes:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except:
                proc.kill()
    
    def run_demo(self, with_failures=False):
        try:
            self.start_coordinator()
            failure_rate = 0.3 if with_failures else 0.0
            self.start_participant('Node1', 5001, 0.0)
            self.start_participant('Node2', 5002, failure_rate)
            self.start_participant('Node3', 5003, 0.0)
            print("\nAll components started. Waiting...")
            time.sleep(3)
            self.run_client()
            print("\nDemo complete! Press Ctrl+C to stop.")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nInterrupted by user.")
        finally:
            self.stop_all()

if __name__ == "__main__":
    print("=" * 60)
    print("DISTRIBUTED TRANSACTION SYSTEM")
    print("=" * 60)
    print("\n1. Run Normal Demo")
    print("2. Run Demo with Failures")
    choice = input("\nSelect option: ").strip()
    runner = SystemRunner()
    if choice == '1':
        runner.run_demo(with_failures=False)
    elif choice == '2':
        runner.run_demo(with_failures=True)
