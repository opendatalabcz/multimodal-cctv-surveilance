import requests
import json
import base64
import os
import time
import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
from typing import Dict, List, Optional, Union, Any, Tuple
from pathlib import Path
import hashlib


class CameraImageFetcher:
    """
    Class for downloading images from Prague security cameras
    """
    
    def __init__(self, output_dir: str = "camera_images", timeout: int = 30, verbose: bool = True):
        """
        Initialize Prague Camera Fetcher
        
        Args:
            output_dir (str): Default folder for saving images
            timeout (int): Timeout for HTTP requests in seconds
            verbose (bool): Whether to print detailed information
        """
        self.base_url = "https://bezpecnost.praha.eu/Intens.CrisisPortalInfrastructureApp/cameras"
        self.output_dir = output_dir
        self.timeout = timeout
        self.verbose = verbose
        
        # HTTP headers for browser simulation
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'cs-CZ,cs;q=0.9,en;q=0.8',
        }
        
        # Async session (will be initialized on first use)
        self._session = None
        
        # Create output folder
        os.makedirs(self.output_dir, exist_ok=True)
    
    
    def _print(self, message: str):
        """Print message if verbose is enabled"""
        if self.verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
    
    def _get_camera_url(self, camera_id: str) -> str:
        """Builds URL for specific camera"""
        return f"{self.base_url}/{camera_id}/image"
    
    def _parse_time_string(self, time_str: str) -> timedelta:
        """
        Parses text time notation to timedelta
        
        Supported formats:
        - "30s" = 30 seconds, "5m" = 5 minutes, "2h" = 2 hours, "3d" = 3 days
        """
        if not isinstance(time_str, str):
            raise ValueError("Time string must be a string")
        
        # Simple parsing without regex
        time_str = time_str.lower().strip()
        
        if time_str.endswith('s'):
            return timedelta(seconds=int(time_str[:-1]))
        elif time_str.endswith('m'):
            return timedelta(minutes=int(time_str[:-1]))
        elif time_str.endswith('h'):
            return timedelta(hours=int(time_str[:-1]))
        elif time_str.endswith('d'):
            return timedelta(days=int(time_str[:-1]))
        else:
            raise ValueError(f"Invalid time format: {time_str}. Use formats like '5m', '2h', '1d'")
    
    def _normalize_interval(self, interval: Union[str, timedelta, int]) -> timedelta:
        """Normalizes interval to timedelta"""
        if isinstance(interval, timedelta):
            return interval
        elif isinstance(interval, str):
            return self._parse_time_string(interval)
        elif isinstance(interval, (int, float)):
            return timedelta(seconds=interval)
        else:
            raise ValueError("Interval must be string, timedelta, or number")
    
    async def _get_session(self):
        """Gets or creates async HTTP session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=timeout
            )
        return self._session
    
    async def _close_session(self):
        """Closes async HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()
            
    def fetch_camera_image(self, camera_id: str, save_to_file: bool = True, 
                          custom_output_dir: Optional[str] = None) -> Optional[Dict]:
        """
        Downloads and decodes image from Prague security camera
        
        Args:
            camera_id (str): Camera ID
            save_to_file (bool): Whether to save image to file
            custom_output_dir (str, optional): Custom output folder
            
        Returns:
            Dict: Information about downloaded image or None on error
        """
        output_dir = custom_output_dir or self.output_dir
        
        # Create output folder if it doesn't exist
        if save_to_file:
            os.makedirs(output_dir, exist_ok=True)
        
        url = self._get_camera_url(camera_id)
        
        self._print(f"Downloading data from camera {camera_id}...")
        
        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                base64_data = data.get('contentBase64')
                
                if base64_data:
                    # Decoding base64 image
                    image_bytes = base64.b64decode(base64_data)
                    img = Image.open(BytesIO(image_bytes))
                    
                    if save_to_file:
                        # Save image
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"camera_{camera_id}_{timestamp}.jpg"
                        filepath = os.path.join(output_dir, filename)
                        
                        img.save(filepath)
                        self._print(f"✅ Image saved: {filename}")
                        
                        return {
                            'success': True,
                            'camera_id': camera_id,
                            'filename': filename,
                            'filepath': filepath,
                            'dimensions': img.size,
                            'size_bytes': len(image_bytes)
                        }
                    else:
                        return {
                            'success': True,
                            'camera_id': camera_id,
                            'dimensions': img.size,
                            'size_bytes': len(image_bytes)
                        }
                else:
                    self._print("⚠️ No base64 data found in response")
            else:
                self._print(f"❌ HTTP Error: {response.status_code}")
                
        except Exception as e:
            self._print(f"❌ Error: {e}")
        
        return None
    
    async def fetch_camera_image_async(self, camera_id: str, save_to_file: bool = True, 
                                     custom_output_dir: Optional[str] = None) -> Optional[Dict]:
        """Asynchronously downloads image from camera"""
        output_dir = custom_output_dir or self.output_dir
        
        # Create output folder if it doesn't exist
        if save_to_file:
            os.makedirs(output_dir, exist_ok=True)
        
        url = self._get_camera_url(camera_id)
        session = await self._get_session()
        
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    base64_data = data.get('contentBase64')
                    
                    if base64_data:
                        image_bytes = base64.b64decode(base64_data)
                        img = Image.open(BytesIO(image_bytes))
                        
                        if save_to_file:
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename = f"camera_{camera_id}_{timestamp}.jpg"
                            filepath = os.path.join(output_dir, filename)
                            
                            img.save(filepath)
                            self._print(f"✅ [ASYNC] {camera_id}: {filename}")
                            
                            return {
                                'success': True,
                                'camera_id': camera_id,
                                'filename': filename,
                                'filepath': filepath,
                                'dimensions': img.size,
                                'size_bytes': len(image_bytes)
                            }
                        else:
                            self._print(f"✅ [ASYNC] {camera_id}: image loaded (not saved)")
                            return {
                                'success': True,
                                'camera_id': camera_id,
                                'dimensions': img.size,
                                'size_bytes': len(image_bytes)
                            }
        except Exception as e:
            self._print(f"❌ [ASYNC] {camera_id}: {e}")
        
        return None

    def fetch_multiple_parallel(self, camera_ids: List[str], 
                           custom_output_dir: Optional[str] = None) -> List[Optional[Dict]]:
        """Parallel async download of multiple cameras with wrapper"""
        return asyncio.run(self.fetch_multiple_async(camera_ids, custom_output_dir))
    
    async def fetch_multiple_async(self, camera_ids: List[str], custom_output_dir: Optional[str] = None):
        """Async parallel fetch of multiple cameras"""
        tasks = [self.fetch_camera_image_async(cam_id, True, custom_output_dir) for cam_id in camera_ids]
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        duration = time.time() - start_time
        
        successful = sum(1 for r in results if r and not isinstance(r, Exception))
        self._print(f"🎯 Parallel: {successful}/{len(camera_ids)} cameras in {duration:.1f}s")
        
        await self._close_session()
        return [r if not isinstance(r, Exception) else None for r in results]

    def monitor_simple(self, camera_ids: Union[str, List[str]], 
                     interval: str = "10m", duration: str = "1h",
                     custom_output_dir: Optional[str] = None) -> Dict[str, List[Optional[Dict]]]:
        """Simplified async monitoring with wrapper"""
        return asyncio.run(self.monitor_async(camera_ids, interval, duration, custom_output_dir))
    
    async def monitor_async(self, camera_ids: Union[str, List[str]], 
                           interval: str, duration: str, custom_output_dir: Optional[str]):
        """Asynchronous camera monitoring"""
        if isinstance(camera_ids, str):
            camera_ids = [camera_ids]
        
        # Create output folder if it doesn't exist
        output_dir = custom_output_dir or self.output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        interval_td = self._normalize_interval(interval)
        duration_td = self._normalize_interval(duration)
        iterations = int(duration_td.total_seconds() / interval_td.total_seconds())
        
        self._print(f"🎥 Async monitoring {len(camera_ids)} cameras")
        self._print(f"⏱️ Interval: {interval}, Duration: {duration} ({iterations} iterations)")
        
        all_results = {cam_id: [] for cam_id in camera_ids}
        
        for i in range(iterations):
            self._print(f"🔄 Iteration {i+1}/{iterations}")
            
            # Parallel download from all cameras
            tasks = [self.fetch_camera_image_async(cam_id, True, custom_output_dir) for cam_id in camera_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for j, cam_id in enumerate(camera_ids):
                result = results[j] if not isinstance(results[j], Exception) else None
                all_results[cam_id].append(result)
            
            if i < iterations - 1:
                await asyncio.sleep(interval_td.total_seconds())
        
        await self._close_session()
        self._print("✅ Monitoring completed")
        return all_results
    
    def fetch_multiple_cameras(self, camera_ids: List[str], custom_output_dir: Optional[str] = None) -> List[Optional[Dict]]:
        """Sync version for multiple cameras (slower than async)"""
        
        # Create output folder if it doesn't exist
        output_dir = custom_output_dir or self.output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        results = []
        for camera_id in camera_ids:
            self._print(f"📸 Downloading from camera {camera_id}...")
            result = self.fetch_camera_image(camera_id, save_to_file=True, custom_output_dir=custom_output_dir)
            results.append(result)
        return results
