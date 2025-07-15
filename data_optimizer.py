#!/usr/bin/env python3
"""
Data optimization and API request management for MotmaenBash Data Repository
Optimizes data structure and manages API requests to reduce server load

Features:
- Data compression and optimization
- API request rate limiting and throttling
- Caching mechanisms
- Batch processing
- Memory-efficient data handling
- Request queue management

@version 2.0.0
@author محمدحسین نوروزی (Mohammad Hossein Norouzi)
"""

import json
import os
import time
import asyncio
import aiohttp
import hashlib
import gzip
import sqlite3
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from collections import defaultdict
import threading
from queue import Queue, Empty
import pickle

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class APIRequest:
    """Represents an API request with metadata"""
    url: str
    method: str = 'GET'
    headers: Optional[Dict] = None
    data: Optional[Dict] = None
    priority: int = 1
    retry_count: int = 0
    max_retries: int = 3
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()

class RateLimiter:
    """Rate limiter for API requests"""
    
    def __init__(self, max_requests: int = 100, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []
        self.lock = threading.Lock()
        
    def can_make_request(self) -> bool:
        """Check if we can make a request within rate limits"""
        with self.lock:
            now = time.time()
            # Remove old requests outside time window
            self.requests = [req_time for req_time in self.requests 
                           if now - req_time < self.time_window]
            
            return len(self.requests) < self.max_requests
            
    def record_request(self):
        """Record a new request"""
        with self.lock:
            self.requests.append(time.time())
            
    def get_wait_time(self) -> float:
        """Get time to wait before next request"""
        with self.lock:
            if len(self.requests) == 0:
                return 0.0
                
            oldest_request = min(self.requests)
            time_passed = time.time() - oldest_request
            
            if time_passed >= self.time_window:
                return 0.0
            else:
                return self.time_window - time_passed

class DataCache:
    """Caching system for API responses and data"""
    
    def __init__(self, cache_dir: str = "cache", max_size: int = 1000):
        self.cache_dir = cache_dir
        self.max_size = max_size
        self.db_path = os.path.join(cache_dir, "cache.db")
        self._init_cache()
        
    def _init_cache(self):
        """Initialize cache database"""
        os.makedirs(self.cache_dir, exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                data BLOB,
                timestamp REAL,
                expires_at REAL,
                access_count INTEGER DEFAULT 0,
                size INTEGER
            )
        ''')
        
        conn.commit()
        conn.close()
        
    def get(self, key: str) -> Optional[Any]:
        """Get data from cache"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT data, expires_at FROM cache 
            WHERE key = ? AND expires_at > ?
        ''', (key, time.time()))
        
        result = cursor.fetchone()
        
        if result:
            # Update access count
            cursor.execute('''
                UPDATE cache SET access_count = access_count + 1 
                WHERE key = ?
            ''', (key,))
            conn.commit()
            
            try:
                data = pickle.loads(result[0])
                conn.close()
                return data
            except Exception as e:
                logger.error(f"Cache deserialization error: {e}")
                
        conn.close()
        return None
        
    def set(self, key: str, data: Any, ttl: int = 3600):
        """Set data in cache"""
        try:
            serialized_data = pickle.dumps(data)
            expires_at = time.time() + ttl
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO cache 
                (key, data, timestamp, expires_at, size) 
                VALUES (?, ?, ?, ?, ?)
            ''', (key, serialized_data, time.time(), expires_at, len(serialized_data)))
            
            conn.commit()
            conn.close()
            
            # Clean up old entries if needed
            self._cleanup_cache()
            
        except Exception as e:
            logger.error(f"Cache serialization error: {e}")
            
    def _cleanup_cache(self):
        """Clean up expired and least used cache entries"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Remove expired entries
        cursor.execute('DELETE FROM cache WHERE expires_at < ?', (time.time(),))
        
        # Remove least used entries if over max size
        cursor.execute('SELECT COUNT(*) FROM cache')
        count = cursor.fetchone()[0]
        
        if count > self.max_size:
            entries_to_remove = count - self.max_size
            cursor.execute('''
                DELETE FROM cache WHERE key IN (
                    SELECT key FROM cache 
                    ORDER BY access_count ASC, timestamp ASC 
                    LIMIT ?
                )
            ''', (entries_to_remove,))
            
        conn.commit()
        conn.close()

class RequestQueue:
    """Priority queue for API requests"""
    
    def __init__(self, max_size: int = 1000):
        self.queue = Queue(maxsize=max_size)
        self.processing = False
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'cached_responses': 0
        }
        
    def add_request(self, request: APIRequest) -> bool:
        """Add request to queue"""
        try:
            self.queue.put(request, block=False)
            self.stats['total_requests'] += 1
            return True
        except:
            logger.warning("Request queue is full")
            return False
            
    def get_request(self, timeout: float = 1.0) -> Optional[APIRequest]:
        """Get next request from queue"""
        try:
            return self.queue.get(timeout=timeout)
        except Empty:
            return None
            
    def size(self) -> int:
        """Get queue size"""
        return self.queue.qsize()

class DataOptimizer:
    """Main data optimization and API management class"""
    
    def __init__(self, data_dir: str = "data", cache_dir: str = "cache"):
        self.data_dir = data_dir
        self.cache_dir = cache_dir
        self.rate_limiter = RateLimiter(max_requests=50, time_window=60)  # 50 requests per minute
        self.cache = DataCache(cache_dir)
        self.request_queue = RequestQueue()
        self.session = None
        self.processing_thread = None
        self.stop_processing = False
        
    async def _create_session(self) -> aiohttp.ClientSession:
        """Create HTTP session with proper headers"""
        headers = {
            'User-Agent': 'MotmaenBash-DataOptimizer/2.0.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        
        connector = aiohttp.TCPConnector(
            limit=10,  # Maximum number of connections
            limit_per_host=5,  # Maximum connections per host
            ttl_dns_cache=300,  # DNS cache TTL
            use_dns_cache=True,
        )
        
        timeout = aiohttp.ClientTimeout(
            total=30,  # Total timeout
            connect=10,  # Connection timeout
            sock_read=20  # Socket read timeout
        )
        
        return aiohttp.ClientSession(
            headers=headers,
            connector=connector,
            timeout=timeout
        )
        
    async def make_api_request(self, request: APIRequest) -> Optional[Dict]:
        """Make API request with rate limiting and caching"""
        # Generate cache key
        cache_key = hashlib.md5(
            f"{request.url}:{request.method}:{str(request.data)}".encode()
        ).hexdigest()
        
        # Check cache first
        cached_response = self.cache.get(cache_key)
        if cached_response:
            self.request_queue.stats['cached_responses'] += 1
            logger.info(f"Cache hit for {request.url}")
            return cached_response
            
        # Check rate limit
        if not self.rate_limiter.can_make_request():
            wait_time = self.rate_limiter.get_wait_time()
            logger.info(f"Rate limit exceeded, waiting {wait_time:.2f} seconds")
            await asyncio.sleep(wait_time)
            
        # Make request
        try:
            if not self.session:
                self.session = await self._create_session()
                
            self.rate_limiter.record_request()
            
            async with self.session.request(
                request.method,
                request.url,
                json=request.data,
                headers=request.headers
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    
                    # Cache successful response
                    self.cache.set(cache_key, data, ttl=3600)  # 1 hour TTL
                    
                    self.request_queue.stats['successful_requests'] += 1
                    logger.info(f"Successful request to {request.url}")
                    return data
                    
                elif response.status == 429:  # Rate limited
                    retry_after = int(response.headers.get('Retry-After', 60))
                    logger.warning(f"Rate limited, retrying after {retry_after} seconds")
                    await asyncio.sleep(retry_after)
                    
                    if request.retry_count < request.max_retries:
                        request.retry_count += 1
                        return await self.make_api_request(request)
                        
                else:
                    logger.error(f"Request failed with status {response.status}")
                    
        except asyncio.TimeoutError:
            logger.error(f"Request timeout for {request.url}")
        except Exception as e:
            logger.error(f"Request error: {e}")
            
        self.request_queue.stats['failed_requests'] += 1
        return None
        
    def compress_data(self, data: Dict) -> bytes:
        """Compress data using gzip"""
        json_str = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
        return gzip.compress(json_str.encode('utf-8'))
        
    def decompress_data(self, compressed_data: bytes) -> Dict:
        """Decompress gzip data"""
        json_str = gzip.decompress(compressed_data).decode('utf-8')
        return json.loads(json_str)
        
    def optimize_data_structure(self, data: List) -> Dict:
        """Optimize data structure for better performance"""
        optimized = {
            'version': '2.0.0',
            'timestamp': datetime.now().isoformat(),
            'author': 'محمدحسین نوروزی (Mohammad Hossein Norouzi)',
            'compression': 'gzip',
            'categories': []
        }
        
        total_entries = 0
        total_hashes = 0
        
        for category_idx, category in enumerate(data):
            category_data = {
                'id': category_idx,
                'entries': [],
                'stats': {
                    'entry_count': len(category),
                    'hash_count': 0
                }
            }
            
            for entry in category:
                optimized_entry = {
                    'h': entry['hashes'],  # Shortened field name
                    't': entry['type'],
                    'm': entry['match'],
                    'l': entry['level']
                }
                
                # Remove duplicate hashes
                optimized_entry['h'] = list(set(optimized_entry['h']))
                
                category_data['entries'].append(optimized_entry)
                category_data['stats']['hash_count'] += len(optimized_entry['h'])
                total_hashes += len(optimized_entry['h'])
                
            optimized['categories'].append(category_data)
            total_entries += len(category)
            
        optimized['stats'] = {
            'total_entries': total_entries,
            'total_hashes': total_hashes,
            'categories': len(data)
        }
        
        return optimized
        
    def batch_process_data(self, data: List, batch_size: int = 100) -> List:
        """Process data in batches to reduce memory usage"""
        processed_data = []
        
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            
            # Process batch
            processed_batch = []
            for item in batch:
                # Optimize individual item
                if isinstance(item, dict) and 'hashes' in item:
                    # Remove duplicate hashes
                    item['hashes'] = list(set(item['hashes']))
                    
                    # Validate hashes
                    valid_hashes = []
                    for hash_val in item['hashes']:
                        if isinstance(hash_val, str) and len(hash_val) == 64:
                            valid_hashes.append(hash_val.lower())
                            
                    item['hashes'] = valid_hashes
                    
                processed_batch.append(item)
                
            processed_data.extend(processed_batch)
            
            # Small delay to prevent overwhelming the system
            time.sleep(0.001)
            
        return processed_data
        
    def create_data_index(self, data: List) -> Dict:
        """Create index for faster data lookups"""
        index = {
            'hash_to_entry': {},
            'type_to_entries': defaultdict(list),
            'level_to_entries': defaultdict(list)
        }
        
        for category_idx, category in enumerate(data):
            for entry_idx, entry in enumerate(category):
                entry_ref = {'category': category_idx, 'index': entry_idx}
                
                # Index by hash
                for hash_val in entry['hashes']:
                    index['hash_to_entry'][hash_val] = entry_ref
                    
                # Index by type
                index['type_to_entries'][entry['type']].append(entry_ref)
                
                # Index by level
                index['level_to_entries'][entry['level']].append(entry_ref)
                
        return index
        
    def optimize_file(self, input_file: str, output_file: str = None) -> bool:
        """Optimize a data file"""
        try:
            logger.info(f"Optimizing file: {input_file}")
            
            # Read original file
            with open(input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Process data in batches
            if isinstance(data, list) and len(data) > 0:
                # Check if it's the main data structure
                if isinstance(data[0], list):
                    # Main data.json format
                    optimized_data = self.optimize_data_structure(data)
                    
                    # Create index
                    index = self.create_data_index(data)
                    optimized_data['index'] = index
                    
                else:
                    # Other file formats
                    optimized_data = self.batch_process_data(data)
                    
            else:
                optimized_data = data
                
            # Save optimized file
            if output_file is None:
                name, ext = os.path.splitext(input_file)
                output_file = f"{name}_optimized{ext}"
                
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(optimized_data, f, separators=(',', ':'), ensure_ascii=False)
                
            # Save compressed version
            compressed_file = f"{output_file}.gz"
            compressed_data = self.compress_data(optimized_data)
            with open(compressed_file, 'wb') as f:
                f.write(compressed_data)
                
            # Calculate compression ratio
            original_size = os.path.getsize(input_file)
            optimized_size = os.path.getsize(output_file)
            compressed_size = os.path.getsize(compressed_file)
            
            logger.info(f"Original size: {original_size:,} bytes")
            logger.info(f"Optimized size: {optimized_size:,} bytes")
            logger.info(f"Compressed size: {compressed_size:,} bytes")
            logger.info(f"Compression ratio: {compressed_size/original_size:.2%}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error optimizing file: {e}")
            return False
            
    def start_request_processor(self):
        """Start background request processor"""
        self.stop_processing = False
        self.processing_thread = threading.Thread(target=self._process_requests)
        self.processing_thread.daemon = True
        self.processing_thread.start()
        logger.info("Request processor started")
        
    def stop_request_processor(self):
        """Stop background request processor"""
        self.stop_processing = True
        if self.processing_thread:
            self.processing_thread.join()
        logger.info("Request processor stopped")
        
    def _process_requests(self):
        """Background request processor"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        while not self.stop_processing:
            request = self.request_queue.get_request(timeout=1.0)
            if request:
                try:
                    result = loop.run_until_complete(self.make_api_request(request))
                    if result:
                        logger.info(f"Processed request: {request.url}")
                except Exception as e:
                    logger.error(f"Error processing request: {e}")
                    
        loop.close()
        
    def get_stats(self) -> Dict:
        """Get optimization and request statistics"""
        return {
            'request_queue': {
                'size': self.request_queue.size(),
                'stats': self.request_queue.stats
            },
            'rate_limiter': {
                'requests_in_window': len(self.rate_limiter.requests),
                'max_requests': self.rate_limiter.max_requests,
                'time_window': self.rate_limiter.time_window
            },
            'cache': {
                'cache_dir': self.cache_dir,
                'db_path': self.cache.db_path
            }
        }
        
    async def close(self):
        """Clean up resources"""
        self.stop_request_processor()
        if self.session:
            await self.session.close()

def main():
    """Main function for command line usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Optimize MotmaenBash data files')
    parser.add_argument('input_file', help='Input data file')
    parser.add_argument('--output', help='Output file (default: input_optimized.json)')
    parser.add_argument('--data-dir', default='data', help='Data directory')
    parser.add_argument('--cache-dir', default='cache', help='Cache directory')
    
    args = parser.parse_args()
    
    optimizer = DataOptimizer(args.data_dir, args.cache_dir)
    
    success = optimizer.optimize_file(args.input_file, args.output)
    
    if success:
        print("✅ File optimization completed successfully")
        stats = optimizer.get_stats()
        print(f"📊 Statistics: {json.dumps(stats, indent=2)}")
    else:
        print("❌ File optimization failed")
        exit(1)

if __name__ == '__main__':
    main()