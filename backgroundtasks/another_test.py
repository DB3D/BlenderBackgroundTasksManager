
# NOTE this file should not have any dependencies with Blender

import time

def myfoo(v,):
    """Simple test function for parallel processing"""

    print(f"Processing myfoo({v})")
    
    time.sleep(1.5)  # Simulate work
    
    for i in range(v):
        print("Heyooo")
    
    print(f"Completed myfoo({v})")
    return None

# Test the function by executing this script directly?
if __name__ == "__main__":
    result = myfoo(5)
