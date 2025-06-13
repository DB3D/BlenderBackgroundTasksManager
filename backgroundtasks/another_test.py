
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

def my_looong_task(v,):
    print(f"my_looong_task1")
    time.sleep(1.5)  # Simulate work
    print(f"my_looong_task2")
    time.sleep(1.5)  # Simulate work
    print(f"my_looong_task3")
    time.sleep(1.5)  # Simulate work
    print(f"my_looong_task4")
    time.sleep(1.5)  # Simulate work
    print(f"my_looong_task5")
    time.sleep(1.5)  # Simulate work
    print(f"my_looong_task finished!!")
    return v

# Test the function by executing this script directly?
if __name__ == "__main__":
    result = myfoo(5)
