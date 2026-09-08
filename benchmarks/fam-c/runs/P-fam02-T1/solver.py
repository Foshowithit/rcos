import json
import os

def solve(src_dir, dst_path):
    # Load faults configuration
    faults_path = os.path.join(src_dir, 'faults.json')
    with open(faults_path, 'r') as f:
        faults_data = json.load(f)
    failures = faults_data.get('failures', {})
    
    # Setup log file path (in src_dir)
    log_path = os.path.join(src_dir, 'retry.log')
    # Clear log file
    open(log_path, 'w').close()
    
    merged_items = []
    current_page_name = 'q1.json'
    
    while current_page_name:
        page_key = 'pages/' + current_page_name
        fail_count = failures.get(page_key, 0)
        page_file_path = os.path.join(src_dir, 'pages', current_page_name)
        
        page_read_success = False
        for attempt_num in range(1, 6):  # max 5 attempts
            should_fail_simulated = attempt_num <= fail_count
            
            # Log every attempt
            with open(log_path, 'a') as log_file:
                if should_fail_simulated:
                    log_file.write('Attempt ' + str(attempt_num) + ' for ' + page_key + ': transient failure\n')
                    continue
            
            # Not simulated to fail - attempt real read
            try:
                with open(page_file_path, 'r') as page_file:
                    page_data = json.load(page_file)
                
                with open(log_path, 'a') as log_file:
                    log_file.write('Attempt ' + str(attempt_num) + ' for ' + page_key + ': success\n')
                
                merged_items.extend(page_data.get('items', []))
                next_page = page_data.get('next')
                current_page_name = next_page + '.json' if next_page else None
                page_read_success = True
                break
            except Exception as e:
                with open(log_path, 'a') as log_file:
                    log_file.write('Attempt ' + str(attempt_num) + ' for ' + page_key + ': read error - ' + str(e) + '\n')
        
        if not page_read_success:
            break
    
    # Prepare merged output
    output_data = {'items': merged_items}
    
    # Determine output file path
    if os.path.isdir(dst_path):
        output_file_path = os.path.join(dst_path, 'OUTPUT.json')
    else:
        output_file_path = dst_path
    
    # Ensure parent directory exists
    parent_dir = os.path.dirname(output_file_path)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir)
    
    # Write output
    with open(output_file_path, 'w') as out_file:
        json.dump(output_data, out_file)

if __name__ == '__main__':
    import sys
    if len(sys.argv) >= 3:
        solve(sys.argv[1], sys.argv[2])
