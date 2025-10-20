"""Preview management system for serving local website previews with feedback interface."""

import asyncio
import logging
import os
import tempfile
import threading
from datetime import datetime
from typing import Dict, Optional, Any
from uuid import uuid4
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import socket
from contextlib import closing

from ..core.state_manager import StateManager


logger = logging.getLogger(__name__)


class PreviewServer:
    """Individual preview server for a project."""
    
    def __init__(self, project_id: str, port: int, html_content: str, assets_dir: Optional[str] = None):
        """Initialize preview server.
        
        Args:
            project_id: ID of the project
            port: Port to serve on
            html_content: HTML content to serve
        """
        self.project_id = project_id
        self.port = port
        self.html_content = html_content
        self.app = FastAPI(title=f"Preview Server - {project_id}")
        self.server = None
        self.server_thread = None
        self.is_running = False
        self.temp_dir = None
        self.assets_dir = assets_dir
        
        # Setup CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Setup routes
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup FastAPI routes for the preview server."""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def serve_preview():
            """Serve the main preview page."""
            return HTMLResponse(content=self.html_content)
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {"status": "healthy", "project_id": self.project_id}
        
        @self.app.post("/api/feedback")
        async def submit_feedback(request: Request):
            """Handle feedback submission from the preview interface."""
            try:
                data = await request.json()
                feedback_text = data.get("feedback", "").strip()
                
                if not feedback_text:
                    raise HTTPException(status_code=400, detail="Feedback text is required")
                
                # Log feedback submission
                logger.info(f"Feedback received for project {self.project_id}: {feedback_text[:100]}...")
                
                # Return success response
                # Note: Actual feedback processing will be handled by the main application
                return JSONResponse({
                    "status": "success",
                    "message": "Feedback submitted successfully",
                    "project_id": self.project_id,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
            except Exception as e:
                logger.error(f"Error handling feedback submission: {str(e)}")
                raise HTTPException(status_code=500, detail="Failed to submit feedback")

        # Serve uploaded assets when available
        if self.assets_dir and os.path.isdir(self.assets_dir):
            self.app.mount("/assets", StaticFiles(directory=self.assets_dir), name=f"assets-{self.project_id}")
    
    def start(self):
        """Start the preview server in a separate thread."""
        if self.is_running:
            logger.warning(f"Preview server for project {self.project_id} is already running")
            return
        
        def run_server():
            """Run the server in a separate thread."""
            try:
                config = uvicorn.Config(
                    self.app,
                    host="127.0.0.1",
                    port=self.port,
                    log_level="warning",  # Reduce log noise
                    access_log=False
                )
                self.server = uvicorn.Server(config)
                asyncio.run(self.server.serve())
            except Exception as e:
                logger.error(f"Error running preview server for project {self.project_id}: {str(e)}")
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        self.is_running = True
        
        logger.info(f"Preview server started for project {self.project_id} on port {self.port}")
    
    def stop(self):
        """Stop the preview server."""
        if not self.is_running:
            return
        
        try:
            if self.server:
                self.server.should_exit = True
            
            if self.server_thread and self.server_thread.is_alive():
                self.server_thread.join(timeout=5)
            
            self.is_running = False
            logger.info(f"Preview server stopped for project {self.project_id}")
            
        except Exception as e:
            logger.error(f"Error stopping preview server for project {self.project_id}: {str(e)}")
        
        # Cleanup temp directory if created
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                import shutil
                shutil.rmtree(self.temp_dir)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp directory: {str(e)}")
    
    def update_content(self, html_content: str):
        """Update the HTML content served by the preview server.
        
        Args:
            html_content: New HTML content to serve
        """
        self.html_content = html_content
        logger.info(f"Updated content for preview server {self.project_id}")


class PreviewManager:
    """Manages preview servers for multiple projects."""
    
    def __init__(self, state_manager: Optional[StateManager] = None):
        """Initialize the preview manager.
        
        Args:
            state_manager: State manager for persisting preview data
        """
        self.state_manager = state_manager
        self.active_servers: Dict[str, PreviewServer] = {}
        self.port_range_start = 8080
        self.port_range_end = 8180
        self.used_ports = set()
    
    def _find_available_port(self) -> int:
        """Find an available port for a new preview server.
        
        Returns:
            int: Available port number
            
        Raises:
            RuntimeError: If no available port is found
        """
        for port in range(self.port_range_start, self.port_range_end):
            if port not in self.used_ports:
                # Check if port is actually available
                with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                    try:
                        sock.bind(('127.0.0.1', port))
                        self.used_ports.add(port)
                        return port
                    except OSError:
                        continue
        
        raise RuntimeError("No available ports for preview server")
    
    def _release_port(self, port: int):
        """Release a port back to the available pool.
        
        Args:
            port: Port number to release
        """
        self.used_ports.discard(port)
    
    async def start_preview_server(self, project_id: str, html_content: str, assets_dir: Optional[str] = None) -> str:
        """Start a preview server for a project.
        
        Args:
            project_id: ID of the project
            html_content: HTML content to serve with feedback interface injected
            assets_dir: Optional directory containing project asset files
            
        Returns:
            str: Preview URL
            
        Raises:
            RuntimeError: If server cannot be started
        """
        logger.info(f"Starting preview server for project {project_id}")
        
        # Stop existing server if running
        if project_id in self.active_servers:
            await self.stop_preview_server(project_id)
        
        try:
            # Inject feedback interface into HTML content
            enhanced_html = self.inject_feedback_interface(project_id, html_content)
            
            # Find available port
            port = self._find_available_port()
            
            # Create and start server
            server = PreviewServer(project_id, port, enhanced_html, assets_dir=assets_dir)
            server.start()
            
            # Store server reference
            self.active_servers[project_id] = server
            
            # Generate preview URL
            preview_url = f"http://127.0.0.1:{port}"
            
            # Persist preview data
            if self.state_manager:
                await self._persist_preview_data(project_id, preview_url, port)
            
            logger.info(f"Preview server started for project {project_id} at {preview_url}")
            return preview_url
            
        except Exception as e:
            logger.error(f"Failed to start preview server for project {project_id}: {str(e)}")
            raise RuntimeError(f"Failed to start preview server: {str(e)}")
    
    async def stop_preview_server(self, project_id: str) -> bool:
        """Stop a preview server for a project.
        
        Args:
            project_id: ID of the project
            
        Returns:
            bool: True if server was stopped successfully
        """
        logger.info(f"Stopping preview server for project {project_id}")
        
        server = self.active_servers.get(project_id)
        if not server:
            logger.warning(f"No active preview server found for project {project_id}")
            return False
        
        try:
            # Release the port
            self._release_port(server.port)
            
            # Stop the server
            server.stop()
            
            # Remove from active servers
            del self.active_servers[project_id]
            
            # Clean up persisted data
            if self.state_manager:
                await self._cleanup_preview_data(project_id)
            
            logger.info(f"Preview server stopped for project {project_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping preview server for project {project_id}: {str(e)}")
            return False
    
    def get_preview_url(self, project_id: str) -> Optional[str]:
        """Get the preview URL for a project.
        
        Args:
            project_id: ID of the project
            
        Returns:
            Optional[str]: Preview URL if server is running, None otherwise
        """
        server = self.active_servers.get(project_id)
        if server and server.is_running:
            return f"http://127.0.0.1:{server.port}"
        return None
    
    def inject_feedback_interface(self, project_id: str, html_content: str) -> str:
        """Inject feedback interface into HTML content.
        
        Args:
            html_content: Original HTML content
            
        Returns:
            str: HTML content with feedback interface injected
        """
        logger.debug("Injecting feedback interface into HTML content")
        
        # Feedback interface HTML and JavaScript
        feedback_interface = """
        <!-- Feedback Interface -->
        <div id="feedback-overlay" style="position: fixed; top: 0; right: 0; width: 350px; height: 100vh; background: rgba(0, 0, 0, 0.9); color: white; padding: 20px; box-sizing: border-box; z-index: 10000; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; overflow-y: auto; transform: translateX(100%); transition: transform 0.3s ease;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h3 style="margin: 0; color: #4CAF50;">Website Feedback</h3>
                <button onclick="toggleFeedback()" style="background: none; border: none; color: white; font-size: 20px; cursor: pointer; padding: 5px;">×</button>
            </div>
            <div style="margin-bottom: 20px;">
                <p style="font-size: 14px; line-height: 1.4; margin-bottom: 15px;">
                    Review your website and provide feedback for improvements, or approve it for deployment.
                </p>
            </div>
            <div style="margin-bottom: 20px;">
                <label style="display: block; margin-bottom: 8px; font-weight: 500;">Your Feedback:</label>
                <textarea id="feedback-text" placeholder="Describe any changes you'd like to make..." style="width: 100%; height: 120px; padding: 10px; border: 1px solid #555; border-radius: 4px; background: #333; color: white; font-size: 14px; resize: vertical; box-sizing: border-box;"></textarea>
            </div>
            <div style="display: flex; flex-direction: column; gap: 10px;">
                <button onclick="submitFeedback()" style="background: #2196F3; color: white; border: none; padding: 12px 20px; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: 500;">Submit Feedback & Regenerate</button>
                <button onclick="approveForDeployment()" style="background: #4CAF50; color: white; border: none; padding: 12px 20px; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: 500;">Approve for Deployment</button>
            </div>
            <div id="feedback-status" style="margin-top: 15px; padding: 10px; border-radius: 4px; font-size: 13px; display: none;"></div>
        </div>

        <!-- Feedback Toggle Button -->
        <button id="feedback-toggle" onclick="toggleFeedback()" style="position: fixed; top: 20px; right: 20px; background: #4CAF50; color: white; border: none; padding: 12px 16px; border-radius: 50px; cursor: pointer; font-size: 14px; font-weight: 500; z-index: 9999; box-shadow: 0 4px 12px rgba(0,0,0,0.3); transition: all 0.3s ease;">💬 Feedback</button>

        <script>
            const previewParams = new URLSearchParams(window.location.search);
            let apiBase = previewParams.get('apiHost');
            if (apiBase) {
                try {
                    apiBase = decodeURIComponent(apiBase);
                } catch (error) {
                    console.warn('Failed to decode apiHost parameter', error);
                }
            }
            if (!apiBase) {
                const defaultPort = window.location.protocol === 'https:' ? '' : ':8000';
                apiBase = `${window.location.protocol}//${window.location.hostname}${defaultPort}`;
            }

            function buildApiUrl(path) {
                if (!path.startsWith('/')) {
                    path = '/' + path;
                }
                const normalizedBase = apiBase.endsWith('/') ? apiBase.slice(0, -1) : apiBase;
                return normalizedBase + path;
            }

            let feedbackOpen = false;

            function toggleFeedback() {
                const overlay = document.getElementById('feedback-overlay');
                const toggle = document.getElementById('feedback-toggle');
                feedbackOpen = !feedbackOpen;

                if (feedbackOpen) {
                    overlay.style.transform = 'translateX(0)';
                    toggle.style.right = '370px';
                } else {
                    overlay.style.transform = 'translateX(100%)';
                    toggle.style.right = '20px';
                }
            }

            async function submitFeedback() {
                const feedbackText = document.getElementById('feedback-text').value.trim();
                if (!feedbackText) {
                    showStatus('Please enter your feedback before submitting.', 'error');
                    return;
                }

                showStatus('Submitting feedback and regenerating...', 'info');

                try {
                    const response = await fetch(buildApiUrl('/api/projects/__PROJECT_ID__/feedback'), {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            feedback_text: feedbackText,
                            feedback_type: 'improvement'
                        })
                    });

                    if (response.ok) {
                        showStatus('Feedback submitted! Regenerating website...', 'success');
                        setTimeout(() => {
                            window.location.reload();
                        }, 2000);
                    } else {
                        const error = await response.json().catch(() => ({}));
                        showStatus('Error: ' + (error.detail || 'Failed to submit feedback'), 'error');
                    }
                } catch (error) {
                    console.error('Error submitting feedback:', error);
                    showStatus('Error: Failed to submit feedback', 'error');
                }
            }

            async function approveForDeployment() {
                showStatus('Approving for deployment...', 'info');

                try {
                    const response = await fetch(buildApiUrl('/api/approvals/approve'), {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            project_id: '__PROJECT_ID__',
                            approval_type: 'feedback_review'
                        })
                    });

                    if (response.ok) {
                        showStatus('Approved! Proceeding to deployment...', 'success');
                        setTimeout(() => {
                            showStatus('Deployment in progress. You can close this preview tab.', 'info');
                        }, 2000);
                    } else {
                        const error = await response.json().catch(() => ({}));
                        showStatus('Error: ' + (error.detail || 'Failed to approve'), 'error');
                    }
                } catch (error) {
                    console.error('Error approving deployment:', error);
                    showStatus('Error: Failed to approve for deployment', 'error');
                }
            }

            function showStatus(message, type) {
                const status = document.getElementById('feedback-status');
                status.textContent = message;
                status.style.display = 'block';

                if (type === 'success') {
                    status.style.background = '#4CAF50';
                } else if (type === 'error') {
                    status.style.background = '#f44336';
                } else {
                    status.style.background = '#2196F3';
                }

                if (type === 'success' || type === 'error') {
                    setTimeout(() => {
                        status.style.display = 'none';
                    }, 5000);
                }
            }

            document.getElementById('feedback-text').addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && e.ctrlKey) {
                    submitFeedback();
                }
            });

            setTimeout(() => {
                toggleFeedback();
            }, 1000);
        </script>
        """
        
        feedback_interface = feedback_interface.replace("__PROJECT_ID__", project_id)

        # Try to inject before closing body tag, fallback to end of content
        if '</body>' in html_content:
            html_content = html_content.replace('</body>', f'{feedback_interface}</body>')
        else:
            html_content += feedback_interface
        
        return html_content
    
    async def update_preview_content(self, project_id: str, html_content: str) -> bool:
        """Update the content of an existing preview server.
        
        Args:
            project_id: ID of the project
            html_content: New HTML content to serve
            
        Returns:
            bool: True if content was updated successfully
        """
        server = self.active_servers.get(project_id)
        if not server:
            logger.warning(f"No active preview server found for project {project_id}")
            return False
        
        try:
            # Inject feedback interface into new content
            enhanced_html = self.inject_feedback_interface(project_id, html_content)
            
            # Update server content
            server.update_content(enhanced_html)
            
            logger.info(f"Updated preview content for project {project_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating preview content for project {project_id}: {str(e)}")
            return False
    
    async def cleanup_all_previews(self):
        """Stop all active preview servers and cleanup resources."""
        logger.info("Cleaning up all preview servers")
        
        project_ids = list(self.active_servers.keys())
        for project_id in project_ids:
            await self.stop_preview_server(project_id)
        
        self.used_ports.clear()
        logger.info("All preview servers cleaned up")
    
    def get_active_previews(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all active preview servers.
        
        Returns:
            Dict[str, Dict[str, Any]]: Dictionary of project_id -> server info
        """
        return {
            project_id: {
                "url": f"http://127.0.0.1:{server.port}",
                "port": server.port,
                "is_running": server.is_running
            }
            for project_id, server in self.active_servers.items()
        }
    
    async def _persist_preview_data(self, project_id: str, preview_url: str, port: int):
        """Persist preview server data.
        
        Args:
            project_id: ID of the project
            preview_url: Preview URL
            port: Server port
        """
        if not self.state_manager:
            return
        
        try:
            preview_data = {
                "project_id": project_id,
                "preview_url": preview_url,
                "port": port,
                "created_at": datetime.utcnow().isoformat(),
                "status": "active"
            }
            
            await self.state_manager.store_data(
                f"preview_{project_id}",
                preview_data
            )
            
        except Exception as e:
            logger.error(f"Failed to persist preview data for project {project_id}: {str(e)}")
    
    async def _cleanup_preview_data(self, project_id: str):
        """Clean up persisted preview data.
        
        Args:
            project_id: ID of the project
        """
        if not self.state_manager:
            return
        
        try:
            await self.state_manager.delete_data(f"preview_{project_id}")
        except Exception as e:
            logger.error(f"Failed to cleanup preview data for project {project_id}: {str(e)}")