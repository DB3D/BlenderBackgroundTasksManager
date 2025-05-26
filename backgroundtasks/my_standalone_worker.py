#!/usr/bin/env python3
# NOTE this file should not have any dependencies with Blender

import time

def mytask(v):
    """Simple test function for parallel processing"""
    print(f"Processing: {v}")
    time.sleep(1.5)  # Simulate work
    print(f"Completed: {v}")
    return v * 2

# Test the function by executing this script directly?
if __name__ == "__main__":
    print("Testing standalone worker...")
    result = mytask(5)
    print(f"Result: {result}") 