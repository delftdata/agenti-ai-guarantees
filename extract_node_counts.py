import re
import sys

def extract_node_counts(filepath):
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"File not found: {filepath}")
        return

    experiments = []
    current_experiment = None
    in_mermaid = False
    node_count = 0

    for line in lines:
        line = line.strip()
        
        # Look for experiment headers: exactly "### <task> - <model> harness"
        if line.startswith("### ") and " harness" in line.lower() and not "repetition" in line.lower():
            if current_experiment and current_experiment['node_count'] > 0:
                experiments.append(current_experiment)
            
            # Clean up the header (remove the " (X nodes)" if it's there)
            header_title = re.sub(r'\s*\(\d+\s*nodes\)', '', line[4:].strip())
            current_experiment = {'title': header_title, 'node_count': 0}
            in_mermaid = False
            
        elif current_experiment and line.startswith("```mermaid"):
            # Only process the first mermaid block for each experiment header
            if current_experiment['node_count'] == 0:
                in_mermaid = True
                
        elif in_mermaid and line.startswith("```"):
            in_mermaid = False
            # We found the first mermaid graph for this header, save and reset
            experiments.append(current_experiment)
            current_experiment = None
            
        elif in_mermaid:
            # Match node declarations like "fix_validators[fix_validators]"
            # Ignore edges (-->) and style declarations
            if "[" in line and "]" in line and "-->" not in line and not line.startswith("style"):
                current_experiment['node_count'] += 1
                
    # Catch the last one if applicable
    if current_experiment and current_experiment['node_count'] > 0:
        experiments.append(current_experiment)

    # Print results
    print(f"{'Experiment':<50} | {'Node Count'}")
    print("-" * 65)
    
    # Deduplicate by lowercase title
    seen = set()
    for exp in experiments:
        title_lower = exp['title'].lower()
        if title_lower not in seen:
            print(f"{exp['title']:<50} | {exp['node_count']}")
            seen.add(title_lower)

if __name__ == "__main__":
    filepath = "topo-lab/docs/experiment.md"
    extract_node_counts(filepath)
