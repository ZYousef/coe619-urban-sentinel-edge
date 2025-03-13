import subprocess

def run_script(script_name):
    """ Function to run a Python script """
    try:
        subprocess.run(['python', script_name], check=True)
    except subprocess.CalledProcessError:
        print(f"Failed to execute {script_name}")

def main():
    while True:
        # Run download_loop.py
        run_script('helpers/download_loop.py')
        
        # Run fake-location.py
        run_script('helpers/fake-location.py')
        
        # Run main.py
        run_script('python3 -m accident_detector.main')

if __name__ == "__main__":
    main()
