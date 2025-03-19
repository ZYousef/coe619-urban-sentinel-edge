import subprocess
import os

def run_script(script_name, *args, is_module=False):
    """Function to run a Python script or module with optional arguments"""
    command = ['python3']
    if is_module:
        command.extend(['-m', script_name])
    else:
        command.append(script_name)
    command.extend(args)
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError:
        print(f"Failed to execute {script_name} with args {args}")

def main():
    while True:
        # Run download_loop.py
        script_path = os.path.join('helpers', 'download_loop.py')
        run_script(script_path)
        
        # Run fake-location.py
        script_path = os.path.join('helpers', 'fake-location.py')
        run_script(script_path)
        
        # Run accident_detector.main as a module with --debug
        run_script('accident_detector.main', '--debug', is_module=True)

if __name__ == "__main__":
    main()