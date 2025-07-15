#!/usr/bin/env python3
"""
Advanced API Request Manager for MotmaenBash Data Repository
Manages API requests with intelligent rate limiting, caching, and load balancing

Features:
- Adaptive rate limiting based on server response
- Intelligent retry mechanisms with exponential backoff
- Request prioritization and queue management
- Circuit breaker pattern for API protection
- Load balancing across multiple endpoints
- Comprehensive monitoring and analytics

@version 2.0.0
@author محمدحسین نوروزی (Mohammad Hossein Norouzi)
"""

import asyncio
import json
import time
import logging
import hashlib
import statistics
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from collections import deque, defaultdict
import random
import threading
from concurrent.futures import ThreadPoolExecutor
import os

# Try to import aiohttp, fallback if not available
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    print("Warning: aiohttp not available, some features will be disabled")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RequestPriority(Enum):
    """Request priority levels"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

@dataclass
class APIEndpoint:
    """Represents an API endpoint with health metrics"""
    url: str
    weight: int = 1
    health_score: float = 1.0
    last_error: Optional[datetime] = None
    error_count: int = 0
    success_count: int = 0
    response_times: deque = field(default_factory=lambda: deque(maxlen=100))
    
    @property
    def avg_response_time(self) -> float:
        """Calculate average response time"""
        if not self.response_times:
            return 0.0
        return statistics.mean(self.response_times)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        total = self.success_count + self.error_count
        if total == 0:
            return 1.0
        return self.success_count / total

@dataclass
class APIRequest:
    """Enhanced API request with metadata"""
    url: str
    method: str = 'GET'
    data: Optional[Dict] = None
    headers: Optional[Dict] = None
    priority: RequestPriority = RequestPriority.NORMAL
    timeout: float = 30.0
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = field(default_factory=datetime.now)
    callback: Optional[Callable] = None
    context: Optional[Dict] = None
    
    def __post_init__(self):
        if isinstance(self.priority, int):
            self.priority = RequestPriority(self.priority)

class AdaptiveRateLimiter:
    """Adaptive rate limiter that adjusts based on server response"""
    
    def __init__(self, initial_rate: float = 10.0, min_rate: float = 1.0, max_rate: float = 100.0):
        self.current_rate = initial_rate
        self.min_rate = min_rate
        self.max_rate = max_rate
        self.last_request_time = 0.0
        self.request_times = deque(maxlen=100)
        self.success_count = 0
        self.error_count = 0
        self.lock = threading.Lock()
        
    def can_make_request(self) -> bool:
        """Check if we can make a request"""
        with self.lock:
            now = time.time()
            time_since_last = now - self.last_request_time
            return time_since_last >= (1.0 / self.current_rate)
            
    def record_request(self, success: bool, response_time: float = 0.0):
        """Record request result and adapt rate"""
        with self.lock:
            now = time.time()
            self.last_request_time = now
            self.request_times.append(now)
            
            if success:
                self.success_count += 1
                # Gradually increase rate on success
                self.current_rate = min(self.current_rate * 1.05, self.max_rate)
            else:
                self.error_count += 1
                # Decrease rate on error
                self.current_rate = max(self.current_rate * 0.8, self.min_rate)
                
            # Clean old request times
            cutoff_time = now - 60  # Keep last minute
            while self.request_times and self.request_times[0] < cutoff_time:
                self.request_times.popleft()
                
    def get_wait_time(self) -> float:
        """Get time to wait before next request"""
        with self.lock:
            now = time.time()
            time_since_last = now - self.last_request_time
            required_interval = 1.0 / self.current_rate
            return max(0.0, required_interval - time_since_last)
            
    def get_stats(self) -> Dict:
        """Get rate limiter statistics"""
        with self.lock:
            total_requests = self.success_count + self.error_count
            return {
                'current_rate': self.current_rate,
                'success_rate': self.success_count / total_requests if total_requests > 0 else 0,
                'total_requests': total_requests,
                'recent_requests': len(self.request_times)
            }

class CircuitBreaker:
    """Circuit breaker for API protection"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0, success_threshold: int = 3):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.lock = threading.Lock()
        
    def can_make_request(self) -> bool:
        """Check if circuit allows request"""
        with self.lock:
            if self.state == CircuitState.CLOSED:
                return True
            elif self.state == CircuitState.OPEN:
                if self.last_failure_time and time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    return True
                return False
            elif self.state == CircuitState.HALF_OPEN:
                return True
            return False
            
    def record_success(self):
        """Record successful request"""
        with self.lock:
            self.failure_count = 0
            
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.success_count = 0
                    
    def record_failure(self):
        """Record failed request"""
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
            elif self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                
    def get_state(self) -> CircuitState:
        """Get current circuit state"""
        with self.lock:
            return self.state

class LoadBalancer:
    """Load balancer for multiple API endpoints"""
    
    def __init__(self, endpoints: List[str]):
        self.endpoints = [APIEndpoint(url) for url in endpoints]
        self.lock = threading.Lock()
        
    def get_endpoint(self) -> Optional[APIEndpoint]:
        """Get best endpoint based on health and load"""
        with self.lock:
            if not self.endpoints:
                return None
                
            # Filter healthy endpoints
            healthy_endpoints = [ep for ep in self.endpoints if ep.health_score > 0.5]
            
            if not healthy_endpoints:
                # If no healthy endpoints, use the best available
                healthy_endpoints = sorted(self.endpoints, key=lambda x: x.health_score, reverse=True)[:1]
                
            # Weighted random selection based on health score and inverse response time
            weights = []
            for ep in healthy_endpoints:
                weight = ep.health_score * ep.weight
                if ep.avg_response_time > 0:
                    weight /= ep.avg_response_time
                weights.append(weight)
                
            if not weights:
                return healthy_endpoints[0]
                
            # Weighted random selection
            total_weight = sum(weights)
            r = random.uniform(0, total_weight)
            
            cumulative = 0
            for i, weight in enumerate(weights):
                cumulative += weight
                if r <= cumulative:
                    return healthy_endpoints[i]
                    
            return healthy_endpoints[-1]
            
    def record_response(self, endpoint: APIEndpoint, success: bool, response_time: float):
        """Record endpoint response"""
        with self.lock:
            endpoint.response_times.append(response_time)
            
            if success:
                endpoint.success_count += 1
                endpoint.health_score = min(1.0, endpoint.health_score + 0.1)
            else:
                endpoint.error_count += 1
                endpoint.last_error = datetime.now()
                endpoint.health_score = max(0.0, endpoint.health_score - 0.2)
                
    def get_stats(self) -> Dict:
        """Get load balancer statistics"""
        with self.lock:
            return {
                'endpoints': [
                    {
                        'url': ep.url,
                        'health_score': ep.health_score,
                        'success_rate': ep.success_rate,
                        'avg_response_time': ep.avg_response_time,
                        'error_count': ep.error_count,
                        'success_count': ep.success_count
                    }
                    for ep in self.endpoints
                ]
            }

class RequestQueue:
    """Priority queue for API requests"""
    
    def __init__(self, max_size: int = 10000):
        self.queues = {
            RequestPriority.URGENT: deque(),
            RequestPriority.HIGH: deque(),
            RequestPriority.NORMAL: deque(),
            RequestPriority.LOW: deque()
        }
        self.max_size = max_size
        self.total_size = 0
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        
    def add_request(self, request: APIRequest) -> bool:
        """Add request to queue"""
        with self.condition:
            if self.total_size >= self.max_size:
                return False
                
            self.queues[request.priority].append(request)
            self.total_size += 1
            self.condition.notify()
            return True
            
    def get_request(self, timeout: float = 1.0) -> Optional[APIRequest]:
        """Get next request by priority"""
        with self.condition:
            end_time = time.time() + timeout
            
            while self.total_size == 0:
                remaining_time = end_time - time.time()
                if remaining_time <= 0:
                    return None
                self.condition.wait(remaining_time)
                
            # Get highest priority request
            for priority in [RequestPriority.URGENT, RequestPriority.HIGH, RequestPriority.NORMAL, RequestPriority.LOW]:
                if self.queues[priority]:
                    request = self.queues[priority].popleft()
                    self.total_size -= 1
                    return request
                    
            return None
            
    def size(self) -> int:
        """Get queue size"""
        with self.lock:
            return self.total_size
            
    def get_stats(self) -> Dict:
        """Get queue statistics"""
        with self.lock:
            return {
                'total_size': self.total_size,
                'by_priority': {
                    priority.name: len(queue)
                    for priority, queue in self.queues.items()
                }
            }

class APIManager:
    """Main API manager with advanced features"""
    
    def __init__(self, 
                 endpoints: List[str] = None,
                 max_concurrent: int = 10,
                 cache_ttl: int = 3600):
        
        self.endpoints = endpoints or ['https://api.motmaenbash.ir']
        self.max_concurrent = max_concurrent
        self.cache_ttl = cache_ttl
        
        # Initialize components
        self.rate_limiter = AdaptiveRateLimiter()
        self.circuit_breaker = CircuitBreaker()
        self.load_balancer = LoadBalancer(self.endpoints)
        self.request_queue = RequestQueue()
        
        # Session and processing
        self.session = None
        self.processing = False
        self.worker_tasks = []
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent)
        
        # Statistics
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'cached_responses': 0,
            'circuit_breaker_trips': 0,
            'start_time': datetime.now()
        }
        
        # Cache
        self.cache = {}
        self.cache_times = {}
        
    async def start(self):
        """Start the API manager"""
        self.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(
                limit=100,
                limit_per_host=20,
                ttl_dns_cache=300
            ),
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                'User-Agent': 'MotmaenBash-APIManager/2.0.0',
                'Accept': 'application/json'
            }
        )
        
        self.processing = True
        
        # Start worker tasks
        for i in range(self.max_concurrent):
            task = asyncio.create_task(self._worker(f"worker-{i}"))
            self.worker_tasks.append(task)
            
        logger.info(f"API Manager started with {self.max_concurrent} workers")
        
    async def stop(self):
        """Stop the API manager"""
        self.processing = False
        
        # Wait for workers to finish
        if self.worker_tasks:
            await asyncio.gather(*self.worker_tasks, return_exceptions=True)
            
        # Close session
        if self.session:
            await self.session.close()
            
        # Shutdown executor
        self.executor.shutdown(wait=True)
        
        logger.info("API Manager stopped")
        
    async def _worker(self, worker_id: str):
        """Worker task for processing requests"""
        logger.info(f"Worker {worker_id} started")
        
        while self.processing:
            try:
                # Get request from queue
                request = self.request_queue.get_request(timeout=1.0)
                if not request:
                    continue
                    
                # Process request
                result = await self._process_request(request)
                
                # Call callback if provided
                if request.callback:
                    try:
                        if asyncio.iscoroutinefunction(request.callback):
                            await request.callback(result, request.context)
                        else:
                            request.callback(result, request.context)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")
                        
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
                
        logger.info(f"Worker {worker_id} stopped")
        
    async def _process_request(self, request: APIRequest) -> Optional[Dict]:
        """Process individual request"""
        # Check cache first
        cache_key = self._get_cache_key(request)
        cached_result = self._get_from_cache(cache_key)
        if cached_result:
            self.stats['cached_responses'] += 1
            return cached_result
            
        # Check circuit breaker
        if not self.circuit_breaker.can_make_request():
            self.stats['circuit_breaker_trips'] += 1
            logger.warning("Circuit breaker is open, rejecting request")
            return None
            
        # Check rate limiter
        wait_time = self.rate_limiter.get_wait_time()
        if wait_time > 0:
            await asyncio.sleep(wait_time)
            
        # Get endpoint
        endpoint = self.load_balancer.get_endpoint()
        if not endpoint:
            logger.error("No available endpoints")
            return None
            
        # Make request
        start_time = time.time()
        success = False
        result = None
        
        try:
            url = f"{endpoint.url.rstrip('/')}/{request.url.lstrip('/')}"
            
            async with self.session.request(
                request.method,
                url,
                json=request.data,
                headers=request.headers,
                timeout=aiohttp.ClientTimeout(total=request.timeout)
            ) as response:
                
                response_time = time.time() - start_time
                
                if response.status == 200:
                    result = await response.json()
                    success = True
                    self.stats['successful_requests'] += 1
                    
                    # Cache successful response
                    self._cache_result(cache_key, result)
                    
                elif response.status == 429:
                    # Rate limited - back off
                    retry_after = int(response.headers.get('Retry-After', 60))
                    logger.warning(f"Rate limited, backing off for {retry_after}s")
                    await asyncio.sleep(retry_after)
                    
                    # Retry if within limits
                    if request.retry_count < request.max_retries:
                        request.retry_count += 1
                        self.request_queue.add_request(request)
                        
                else:
                    logger.error(f"Request failed with status {response.status}")
                    
        except asyncio.TimeoutError:
            logger.error(f"Request timeout: {request.url}")
        except Exception as e:
            logger.error(f"Request error: {e}")
            
        # Record metrics
        response_time = time.time() - start_time
        self.rate_limiter.record_request(success, response_time)
        self.load_balancer.record_response(endpoint, success, response_time)
        
        if success:
            self.circuit_breaker.record_success()
        else:
            self.circuit_breaker.record_failure()
            self.stats['failed_requests'] += 1
            
        self.stats['total_requests'] += 1
        
        return result
        
    def _get_cache_key(self, request: APIRequest) -> str:
        """Generate cache key for request"""
        key_data = f"{request.method}:{request.url}:{json.dumps(request.data, sort_keys=True)}"
        return hashlib.md5(key_data.encode()).hexdigest()
        
    def _get_from_cache(self, key: str) -> Optional[Dict]:
        """Get result from cache"""
        if key in self.cache:
            cache_time = self.cache_times.get(key, 0)
            if time.time() - cache_time < self.cache_ttl:
                return self.cache[key]
            else:
                # Remove expired entry
                del self.cache[key]
                del self.cache_times[key]
        return None
        
    def _cache_result(self, key: str, result: Dict):
        """Cache result"""
        self.cache[key] = result
        self.cache_times[key] = time.time()
        
        # Simple cache cleanup
        if len(self.cache) > 10000:  # Max 10k cached items
            # Remove oldest 10%
            sorted_keys = sorted(self.cache_times.keys(), key=lambda k: self.cache_times[k])
            keys_to_remove = sorted_keys[:1000]
            for key in keys_to_remove:
                del self.cache[key]
                del self.cache_times[key]
                
    def add_request(self, request: APIRequest) -> bool:
        """Add request to queue"""
        return self.request_queue.add_request(request)
        
    def get_comprehensive_stats(self) -> Dict:
        """Get comprehensive statistics"""
        uptime = datetime.now() - self.stats['start_time']
        
        return {
            'general': {
                **self.stats,
                'uptime_seconds': uptime.total_seconds(),
                'requests_per_second': self.stats['total_requests'] / uptime.total_seconds() if uptime.total_seconds() > 0 else 0
            },
            'rate_limiter': self.rate_limiter.get_stats(),
            'circuit_breaker': {
                'state': self.circuit_breaker.get_state().value,
                'failure_count': self.circuit_breaker.failure_count
            },
            'load_balancer': self.load_balancer.get_stats(),
            'request_queue': self.request_queue.get_stats(),
            'cache': {
                'size': len(self.cache),
                'hit_rate': self.stats['cached_responses'] / self.stats['total_requests'] if self.stats['total_requests'] > 0 else 0
            }
        }
        
    def save_stats(self, filename: str = 'api_stats.json'):
        """Save statistics to file"""
        stats = self.get_comprehensive_stats()
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, default=str, ensure_ascii=False)
        logger.info(f"Statistics saved to {filename}")

async def main():
    """Example usage"""
    # Initialize API manager
    manager = APIManager(
        endpoints=['https://api.motmaenbash.ir', 'https://backup.motmaenbash.ir'],
        max_concurrent=5
    )
    
    try:
        # Start manager
        await manager.start()
        
        # Add some test requests
        for i in range(10):
            request = APIRequest(
                url=f'data/test/{i}',
                priority=RequestPriority.NORMAL,
                context={'test_id': i}
            )
            manager.add_request(request)
            
        # Wait for processing
        await asyncio.sleep(10)
        
        # Print stats
        stats = manager.get_comprehensive_stats()
        print(json.dumps(stats, indent=2, default=str))
        
    finally:
        # Stop manager
        await manager.stop()

if __name__ == '__main__':
    asyncio.run(main())