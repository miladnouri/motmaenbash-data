#!/usr/bin/env python3
"""
Data validation and integrity checker for MotmaenBash Data Repository
Ensures data integrity and validates security information

Security features:
- Hash validation for all data entries
- JSON schema validation
- Data integrity checks
- Security threat detection
- Performance monitoring

@version 2.0.0
@author محمدحسین نوروزی (Mohammad Hossein Norouzi)
"""

import json
import hashlib
import sys
import os
import re
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import argparse

class DataValidator:
    """Validates and secures MotmaenBash data files"""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.errors = []
        self.warnings = []
        self.stats = {
            'total_entries': 0,
            'validated_entries': 0,
            'failed_entries': 0,
            'suspicious_entries': 0
        }
        
    def log_error(self, message: str, file_path: str = None):
        """Log validation error"""
        error_msg = f"ERROR: {message}"
        if file_path:
            error_msg += f" in {file_path}"
        self.errors.append(error_msg)
        print(error_msg, file=sys.stderr)
        
    def log_warning(self, message: str, file_path: str = None):
        """Log validation warning"""
        warning_msg = f"WARNING: {message}"
        if file_path:
            warning_msg += f" in {file_path}"
        self.warnings.append(warning_msg)
        print(warning_msg, file=sys.stderr)
        
    def validate_hash(self, hash_string: str) -> bool:
        """Validate hash format and length"""
        if not hash_string or not isinstance(hash_string, str):
            return False
            
        # Remove leading dash if present (some hashes might have it)
        clean_hash = hash_string.lstrip('-')
        
        # Check SHA-256 hash format (64 hex characters)
        if len(clean_hash) != 64:
            return False
            
        # Check if all characters are hex
        if not re.match(r'^[0-9a-fA-F]{64}$', clean_hash):
            return False
            
        return True
        
    def validate_json_structure(self, data: Any, schema: Dict) -> bool:
        """Validate JSON data against schema"""
        try:
            if schema.get('type') == 'array':
                if not isinstance(data, list):
                    return False
                    
                item_schema = schema.get('items', {})
                for item in data:
                    if not self.validate_json_structure(item, item_schema):
                        return False
                        
            elif schema.get('type') == 'object':
                if not isinstance(data, dict):
                    return False
                    
                required_fields = schema.get('required', [])
                for field in required_fields:
                    if field not in data:
                        return False
                        
                properties = schema.get('properties', {})
                for key, value in data.items():
                    if key in properties:
                        if not self.validate_json_structure(value, properties[key]):
                            return False
                            
            elif schema.get('type') == 'string':
                if not isinstance(data, str):
                    return False
                    
                min_length = schema.get('minLength')
                max_length = schema.get('maxLength')
                
                if min_length and len(data) < min_length:
                    return False
                if max_length and len(data) > max_length:
                    return False
                    
            elif schema.get('type') == 'number':
                if not isinstance(data, (int, float)):
                    return False
                    
                minimum = schema.get('minimum')
                maximum = schema.get('maximum')
                
                if minimum is not None and data < minimum:
                    return False
                if maximum is not None and data > maximum:
                    return False
                    
            return True
            
        except Exception as e:
            self.log_error(f"Schema validation error: {str(e)}")
            return False
            
    def validate_data_json(self, file_path: str) -> bool:
        """Validate main data.json file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if not isinstance(data, list):
                self.log_error("data.json must be an array", file_path)
                return False
                
            for i, category in enumerate(data):
                if not isinstance(category, list):
                    self.log_error(f"Category {i} must be an array", file_path)
                    return False
                    
                for j, entry in enumerate(category):
                    # Handle string entries (legacy format)
                    if isinstance(entry, str):
                        if not self.validate_hash(entry):
                            self.log_error(f"Invalid hash string: {entry}", f"{file_path}[{i}][{j}]")
                            return False
                        self.stats['total_entries'] += 1
                        self.stats['validated_entries'] += 1
                    elif isinstance(entry, dict):
                        if not self.validate_data_entry(entry, f"{file_path}[{i}][{j}]"):
                            return False
                    else:
                        self.log_error(f"Entry must be a string or object, got {type(entry)}", f"{file_path}[{i}][{j}]")
                        return False
                        
            return True
            
        except FileNotFoundError:
            self.log_error(f"File not found: {file_path}")
            return False
        except json.JSONDecodeError as e:
            self.log_error(f"Invalid JSON: {str(e)}", file_path)
            return False
        except Exception as e:
            self.log_error(f"Unexpected error: {str(e)}", file_path)
            return False
            
    def validate_data_entry(self, entry: Dict, location: str) -> bool:
        """Validate individual data entry"""
        self.stats['total_entries'] += 1
        
        # Required fields (flexible based on entry type)
        if 'hashes' in entry:
            # Full entry format
            required_fields = ['hashes', 'type']
            optional_fields = ['match', 'level']
        else:
            self.log_error(f"Missing required field 'hashes'", location)
            self.stats['failed_entries'] += 1
            return False
            
        for field in required_fields:
            if field not in entry:
                self.log_error(f"Missing required field '{field}'", location)
                self.stats['failed_entries'] += 1
                return False
                
        # Validate hashes
        if not isinstance(entry['hashes'], list):
            self.log_error("'hashes' must be an array", location)
            self.stats['failed_entries'] += 1
            return False
            
        if len(entry['hashes']) == 0:
            self.log_error("'hashes' array cannot be empty", location)
            self.stats['failed_entries'] += 1
            return False
            
        # Validate individual hashes
        for i, hash_value in enumerate(entry['hashes']):
            if not self.validate_hash(hash_value):
                self.log_error(f"Invalid hash at index {i}: {hash_value}", location)
                self.stats['failed_entries'] += 1
                return False
                
        # Validate type
        if not isinstance(entry['type'], int) or entry['type'] < 0:
            self.log_error("'type' must be a non-negative integer", location)
            self.stats['failed_entries'] += 1
            return False
            
        # Validate match (optional field)
        if 'match' in entry:
            if isinstance(entry['match'], bool):
                # Convert boolean to integer for consistency
                entry['match'] = int(entry['match'])
            elif not isinstance(entry['match'], int):
                self.log_error("'match' must be an integer or boolean", location)
                self.stats['failed_entries'] += 1
                return False
            elif entry['match'] not in [0, 1, 2]:  # Allow 0, 1, 2 for different match types
                self.log_warning(f"Unusual match value: {entry['match']}", location)
                self.stats['suspicious_entries'] += 1
                
        # Validate level (optional field)
        if 'level' in entry:
            if not isinstance(entry['level'], int) or entry['level'] < 0:
                self.log_error("'level' must be a non-negative integer", location)
                self.stats['failed_entries'] += 1
                return False
            
        # Check for suspicious patterns
        if len(entry['hashes']) > 1000:
            self.log_warning(f"Unusually large number of hashes: {len(entry['hashes'])}", location)
            self.stats['suspicious_entries'] += 1
            
        self.stats['validated_entries'] += 1
        return True
        
    def validate_links_json(self, file_path: str) -> bool:
        """Validate links.json file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if not isinstance(data, list):
                self.log_error("links.json must be an array", file_path)
                return False
                
            for i, link_item in enumerate(data):
                # Handle both string URLs and link objects
                if isinstance(link_item, str):
                    link_url = link_item
                elif isinstance(link_item, dict) and 'link' in link_item:
                    link_url = link_item['link']
                else:
                    self.log_error(f"Link {i} must be a string URL or object with 'link' field", file_path)
                    return False
                    
                # Validate URL format
                if not self.validate_url(link_url):
                    self.log_error(f"Invalid URL format: {link_url}", file_path)
                    return False
                    
                # Check for suspicious URLs
                if self.is_suspicious_url(link_url):
                    self.log_warning(f"Suspicious URL detected: {link_url}", file_path)
                    self.stats['suspicious_entries'] += 1
                    
            return True
            
        except FileNotFoundError:
            self.log_error(f"File not found: {file_path}")
            return False
        except json.JSONDecodeError as e:
            self.log_error(f"Invalid JSON: {str(e)}", file_path)
            return False
        except Exception as e:
            self.log_error(f"Unexpected error: {str(e)}", file_path)
            return False
            
    def validate_url(self, url: str) -> bool:
        """Validate URL format"""
        if not url or not isinstance(url, str):
            return False
            
        # Basic URL validation
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
            
        return url_pattern.match(url) is not None
        
    def is_suspicious_url(self, url: str) -> bool:
        """Check if URL contains suspicious patterns"""
        suspicious_patterns = [
            r'bit\.ly',
            r'tinyurl',
            r'shortened',
            r'redirect',
            r'malware',
            r'phishing',
            r'suspicious',
            r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}',  # IP addresses
            r'[a-z0-9]{32,}',  # Very long random strings
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, url.lower()):
                return True
                
        return False
        
    def validate_tips_json(self, file_path: str) -> bool:
        """Validate tips.json file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if not isinstance(data, list):
                self.log_error("tips.json must be an array", file_path)
                return False
                
            for i, tip in enumerate(data):
                if not isinstance(tip, str):
                    self.log_error(f"Tip {i} must be a string", file_path)
                    return False
                    
                if len(tip.strip()) == 0:
                    self.log_error(f"Tip {i} cannot be empty", file_path)
                    return False
                    
                # Check for suspicious content
                if self.contains_suspicious_content(tip):
                    self.log_warning(f"Suspicious content in tip {i}: {tip[:50]}...", file_path)
                    self.stats['suspicious_entries'] += 1
                    
            return True
            
        except FileNotFoundError:
            self.log_error(f"File not found: {file_path}")
            return False
        except json.JSONDecodeError as e:
            self.log_error(f"Invalid JSON: {str(e)}", file_path)
            return False
        except Exception as e:
            self.log_error(f"Unexpected error: {str(e)}", file_path)
            return False
            
    def contains_suspicious_content(self, content: str) -> bool:
        """Check if content contains suspicious patterns"""
        suspicious_patterns = [
            r'<script',
            r'javascript:',
            r'onload=',
            r'onerror=',
            r'eval\(',
            r'document\.cookie',
            r'window\.location',
            r'alert\(',
            r'confirm\(',
            r'prompt\(',
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, content.lower()):
                return True
                
        return False
        
    def validate_version_json(self, file_path: str) -> bool:
        """Validate version.json file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Handle both simple version format and complex version format
            if 'latest_version_name' in data:
                # Complex version format
                required_fields = ['latest_version_code', 'latest_version_name']
                for field in required_fields:
                    if field not in data:
                        self.log_error(f"Missing required field '{field}'", file_path)
                        return False
                        
                # Validate version code
                if not isinstance(data['latest_version_code'], int):
                    self.log_error("latest_version_code must be an integer", file_path)
                    return False
                    
                # Validate version name
                if not isinstance(data['latest_version_name'], str):
                    self.log_error("latest_version_name must be a string", file_path)
                    return False
                    
            else:
                # Simple version format
                schema = {
                    'type': 'object',
                    'required': ['version', 'last_updated'],
                    'properties': {
                        'version': {'type': 'string', 'minLength': 1},
                        'last_updated': {'type': 'string', 'minLength': 1},
                        'author': {'type': 'string', 'minLength': 1},
                        'description': {'type': 'string', 'minLength': 1}
                    }
                }
                
                if not self.validate_json_structure(data, schema):
                    self.log_error("version.json does not match required schema", file_path)
                    return False
                    
                # Validate version format
                version_pattern = re.compile(r'^\d+\.\d+\.\d+$')
                if not version_pattern.match(data['version']):
                    self.log_error(f"Invalid version format: {data['version']}", file_path)
                    return False
                
            return True
            
        except FileNotFoundError:
            self.log_error(f"File not found: {file_path}")
            return False
        except json.JSONDecodeError as e:
            self.log_error(f"Invalid JSON: {str(e)}", file_path)
            return False
        except Exception as e:
            self.log_error(f"Unexpected error: {str(e)}", file_path)
            return False
            
    def generate_integrity_report(self) -> Dict:
        """Generate data integrity report"""
        return {
            'timestamp': datetime.now().isoformat(),
            'validation_summary': {
                'total_files_checked': 4,
                'errors': len(self.errors),
                'warnings': len(self.warnings),
                'validation_passed': len(self.errors) == 0
            },
            'statistics': self.stats,
            'errors': self.errors,
            'warnings': self.warnings,
            'author': 'محمدحسین نوروزی (Mohammad Hossein Norouzi)',
            'version': '2.0.0'
        }
        
    def validate_all(self) -> bool:
        """Validate all data files"""
        start_time = time.time()
        
        print("Starting MotmaenBash data validation...")
        print(f"Data directory: {self.data_dir}")
        print("-" * 50)
        
        # Define files to validate
        files_to_validate = [
            ('data.json', self.validate_data_json),
            ('links.json', self.validate_links_json),
            ('tips.json', self.validate_tips_json),
            ('version.json', self.validate_version_json)
        ]
        
        all_valid = True
        
        for filename, validator_func in files_to_validate:
            file_path = os.path.join(self.data_dir, filename)
            print(f"Validating {filename}...")
            
            if not validator_func(file_path):
                all_valid = False
                print(f"❌ {filename} validation failed")
            else:
                print(f"✅ {filename} validation passed")
                
        end_time = time.time()
        
        print("-" * 50)
        print(f"Validation completed in {end_time - start_time:.2f} seconds")
        print(f"Total entries processed: {self.stats['total_entries']}")
        print(f"Validated entries: {self.stats['validated_entries']}")
        print(f"Failed entries: {self.stats['failed_entries']}")
        print(f"Suspicious entries: {self.stats['suspicious_entries']}")
        print(f"Errors: {len(self.errors)}")
        print(f"Warnings: {len(self.warnings)}")
        
        if all_valid:
            print("🎉 All validations passed!")
        else:
            print("❌ Some validations failed. Check errors above.")
            
        return all_valid
        
    def save_report(self, output_file: str = "validation_report.json"):
        """Save validation report to file"""
        report = self.generate_integrity_report()
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            
        print(f"Validation report saved to: {output_file}")

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Validate MotmaenBash data files')
    parser.add_argument('--data-dir', default='data', help='Data directory path')
    parser.add_argument('--report', default='validation_report.json', help='Output report file')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    
    args = parser.parse_args()
    
    # Create validator
    validator = DataValidator(args.data_dir)
    
    # Run validation
    success = validator.validate_all()
    
    # Save report
    validator.save_report(args.report)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()