#!/usr/bin/env python3
"""
Simple data validator for GitHub Actions compatibility
Lightweight version without heavy dependencies

@version 2.0.0
@author محمدحسین نوروزی (Mohammad Hossein Norouzi)
"""

import json
import os
import re
import sys
from typing import Dict, List, Any

class SimpleValidator:
    """Simple validator with minimal dependencies"""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.errors = []
        self.warnings = []
        
    def validate_hash(self, hash_string: str) -> bool:
        """Validate hash format"""
        if not hash_string or not isinstance(hash_string, str):
            return False
            
        # Clean hash (remove leading dash if present)
        clean_hash = hash_string.lstrip('-')
        
        # Check SHA-256 format (64 hex characters)
        if len(clean_hash) != 64:
            return False
            
        return re.match(r'^[0-9a-fA-F]{64}$', clean_hash) is not None
        
    def validate_data_json(self, file_path: str) -> bool:
        """Validate main data.json file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if not isinstance(data, list):
                self.errors.append("data.json must be an array")
                return False
                
            for i, category in enumerate(data):
                if isinstance(category, list):
                    for j, entry in enumerate(category):
                        if isinstance(entry, str):
                            # String entry (hash)
                            if not self.validate_hash(entry):
                                self.errors.append(f"Invalid hash at [{i}][{j}]: {entry[:20]}...")
                        elif isinstance(entry, dict):
                            # Object entry
                            if 'hashes' not in entry:
                                self.errors.append(f"Missing 'hashes' field at [{i}][{j}]")
                            elif not isinstance(entry['hashes'], list):
                                self.errors.append(f"'hashes' must be array at [{i}][{j}]")
                            else:
                                for k, hash_val in enumerate(entry['hashes']):
                                    if not self.validate_hash(hash_val):
                                        self.errors.append(f"Invalid hash at [{i}][{j}][{k}]: {hash_val[:20]}...")
                                        
            return len(self.errors) == 0
            
        except FileNotFoundError:
            self.errors.append(f"File not found: {file_path}")
            return False
        except json.JSONDecodeError as e:
            self.errors.append(f"Invalid JSON in {file_path}: {str(e)}")
            return False
        except Exception as e:
            self.errors.append(f"Error validating {file_path}: {str(e)}")
            return False
            
    def validate_json_file(self, file_path: str) -> bool:
        """Validate any JSON file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                json.load(f)
            return True
        except json.JSONDecodeError as e:
            self.errors.append(f"Invalid JSON in {file_path}: {str(e)}")
            return False
        except Exception as e:
            self.errors.append(f"Error reading {file_path}: {str(e)}")
            return False
            
    def validate_all(self) -> bool:
        """Validate all data files"""
        print("Starting simple data validation...")
        
        # Check if data directory exists
        if not os.path.exists(self.data_dir):
            self.errors.append(f"Data directory not found: {self.data_dir}")
            return False
            
        success = True
        
        # Validate main data file
        data_file = os.path.join(self.data_dir, 'data.json')
        if os.path.exists(data_file):
            print("Validating data.json...")
            if not self.validate_data_json(data_file):
                success = False
            else:
                print("✅ data.json validation passed")
        else:
            self.warnings.append("data.json not found")
            
        # Validate other JSON files
        for filename in ['links.json', 'tips.json', 'version.json']:
            file_path = os.path.join(self.data_dir, filename)
            if os.path.exists(file_path):
                print(f"Validating {filename}...")
                if not self.validate_json_file(file_path):
                    success = False
                else:
                    print(f"✅ {filename} validation passed")
            else:
                self.warnings.append(f"{filename} not found")
                
        # Print summary
        print(f"\nValidation Summary:")
        print(f"Errors: {len(self.errors)}")
        print(f"Warnings: {len(self.warnings)}")
        
        if self.errors:
            print("\nErrors found:")
            for error in self.errors:
                print(f"  - {error}")
                
        if self.warnings:
            print("\nWarnings:")
            for warning in self.warnings:
                print(f"  - {warning}")
                
        if success:
            print("\n🎉 Validation passed!")
        else:
            print("\n❌ Validation failed!")
            
        return success
        
    def generate_report(self) -> Dict:
        """Generate simple validation report"""
        return {
            'validation_passed': len(self.errors) == 0,
            'errors': len(self.errors),
            'warnings': len(self.warnings),
            'error_list': self.errors,
            'warning_list': self.warnings
        }

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Simple data validation')
    parser.add_argument('--data-dir', default='data', help='Data directory')
    parser.add_argument('--report', help='Output report file')
    
    args = parser.parse_args()
    
    validator = SimpleValidator(args.data_dir)
    success = validator.validate_all()
    
    if args.report:
        report = validator.generate_report()
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"Report saved to: {args.report}")
        
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()