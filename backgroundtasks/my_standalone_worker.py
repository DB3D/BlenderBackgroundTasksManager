
# NOTE this file should not have any dependencies with Blender

import time

def mytask(v, printhis=None):
    """Simple test function for parallel processing"""

    print(f"Processing mytask({v})")
    
    time.sleep(1.5)  # Simulate work
    
    if (printhis is not None):
        print(f"Printing this: {printhis}")
        return v * 2, 2222
    
    print(f"Completed mytask({v})")
    return v * 2

# Test the function by executing this script directly?
if __name__ == "__main__":
    result = mytask(5)
