"""
Standalone worker module for parallel task processing in Blender addon.
This module must be independent from Blender and contain only functions that can be pickled.
"""

import time
import random


def process_data(data_id, data_name, delay=1.0):
    """
    Process data independently - used for Wave 0 tasks.
    
    Args:
        data_id (int): Unique identifier for the data
        data_name (str): Name/type of the data
        delay (float): Simulated processing time
    
    Returns:
        tuple: (processed_result, metadata)
    """
    print(f"Processing {data_name} (ID: {data_id})...")
    
    # Simulate processing time
    time.sleep(delay)
    
    # Simulate some processing result
    processed_result = {
        'id': data_id,
        'name': data_name,
        'processed_value': data_id * 10 + random.randint(1, 100),
        'status': 'processed'
    }
    
    metadata = {
        'processing_time': delay,
        'worker_function': 'process_data'
    }
    
    print(f"Completed processing {data_name} -> value: {processed_result['processed_value']}")
    return processed_result, metadata


def combine_results(*results, operation="combine"):
    """
    Combine multiple results from previous tasks - used for Wave 1 tasks.
    
    Args:
        *results: Variable number of result values from previous tasks (already resolved by USE_TASK_RESULT)
        operation (str): Type of combination operation
    
    Returns:
        tuple: (combined_result, metadata)
    """
    print(f"Combining {len(results)} results using '{operation}' operation...")
    
    # Results are already the resolved values (not tuples) when using USE_TASK_RESULT
    data_items = list(results)
    
    # Simulate processing time
    time.sleep(0.5)
    
    if operation == "combine":
        # Simple addition of processed values
        total_value = sum(item['processed_value'] for item in data_items)
        combined_result = {
            'operation': operation,
            'input_count': len(data_items),
            'combined_value': total_value,
            'input_ids': [item['id'] for item in data_items],
            'status': 'combined'
        }
    elif operation == "merge":
        # Average of processed values
        avg_value = sum(item['processed_value'] for item in data_items) / len(data_items)
        combined_result = {
            'operation': operation,
            'input_count': len(data_items),
            'merged_value': avg_value,
            'input_ids': [item['id'] for item in data_items],
            'status': 'merged'
        }
    else:
        # Default operation
        combined_result = {
            'operation': 'unknown',
            'input_count': len(data_items),
            'raw_inputs': data_items,
            'status': 'raw'
        }
    
    metadata = {
        'processing_time': 0.5,
        'worker_function': 'combine_results',
        'operation_type': operation
    }
    
    print(f"Combined {len(results)} results -> {combined_result}")
    return combined_result, metadata


def analyze_data(input_result1, input_result2,):
    """
    Analyze combined data - used for Wave 2 tasks.
    """
    print(f"Finalizing...")
    print(input_result1, input_result2)
    return None


if __name__ == "__main__":
    # Test functions locally
    print("Testing worker functions...")
    
    # Test process_data
    result1 = process_data(1, "TestDataA", 0.1)
    result2 = process_data(2, "TestDataB", 0.1)
    print(f"Process results: {result1}, {result2}")
    
    # Test combine_results
    combined = combine_results(result1, result2, operation="combine")
    print(f"Combined result: {combined}")
    
    # Test analyze_data
    analyzed = analyze_data(combined, operation="analyze", depth="deep")
    print(f"Analysis result: {analyzed}")
    
    print("Worker functions test completed!") 