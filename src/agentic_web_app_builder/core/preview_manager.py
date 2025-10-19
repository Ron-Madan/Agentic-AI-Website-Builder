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
    
    def __init__(self, project_id: str, port: int, html_content: str):
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
    
    async def start_preview_server(self, project_id: str, html_content: str) -> str:
        """Start a preview server for a project.
        
        Args:
            project_id: ID of the project
            html_content: HTML content to serve with feedback interface injected
            
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
            enhanced_html = self.inject_feedback_interface(html_content)
            
            # Find available port
            port = self._find_available_port()
            
            # Create and start server
            server = PreviewServer(project_id, port, enhanced_html)
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
    
    def inject_feedback_interface(self, html_content: str) -> str:
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
        <div id="feedback-overlay" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 10000;">
            <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: white; padding: 30px; border-radius: 10px; max-width: 500px; width: 90%;">
                <h3 style="margin-top: 0; color: #333;">Provide Feedback</h3>
                <p style="color: #666; margin-bottom: 20px;">Tell us what you'd like to change about this website:</p>
                <textarea id="feedback-text" placeholder="Describe the changes you'd like to see..." style="width: 100%; height: 120px; padding: 10px; border: 1px solid #ddd; border-radius: 5px; font-family: Arial, sans-serif; resize: vertical;"></textarea>
                <div style="margin-top: 20px; text-align: right;">
                    <button onclick="closeFeedback()" style="background: #ccc; color: #333; border: none; padding: 10px 20px; border-radius: 5px; margin-right: 10px; cursor: pointer;">Cancel</button>
                    <button onclick="submitFeedback()" style="background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer;">Submit Feedback</button>
                </div>
                <div id="feedback-status" style="margin-top: 15px; padding: 10px; border-radius: 5px; display: none;"></div>
            </div>
        </div>
        
        <!-- Feedback Button -->
        <div id="feedback-button" style="position: fixed; bottom: 20px; right: 20px; z-index: 9999;">
            <button onclick="openFeedback()" style="background: #28a745; color: white; border: none; padding: 15px 20px; border-radius: 50px; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.15); font-weight: bold;">
                💬 Give Feedback
            </button>
        </div>
        
        <script>
        function openFeedback() {
            document.getElementById('feedback-overlay').style.display = 'block';
            document.getElementById('feedback-text').focus();
        }
        
        function closeFeedback() {
            document.getElementById('feedback-overlay').style.display = 'none';
            document.getElementById('feedback-text').value = '';
            document.getElementById('feedback-status').style.display = 'none';
        }
        
        async function submitFeedback() {
            const feedbackText = document.getElementById('feedback-text').value.trim();
            const statusDiv = document.getElementById('feedback-status');
            
            if (!feedbackText) {
                showStatus('Please enter your feedback before submitting.', 'error');
                return;
            }
            
            try {
                showStatus('Submitting feedback...', 'info');
                
                const response = await fetch('/api/feedback', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        feedback: feedbackText,
                        timestamp: new Date().toISOString()
                    })
                });
                
                if (response.ok) {
                    showStatus('Feedback submitted successfully! The website will be updated shortly.', 'success');
                    setTimeout(() => {
                        closeFeedback();
                        // Optionally reload the page after a delay to show updates
                        setTimeout(() => window.location.reload(), 2000);
                    }, 2000);
                } else {
                    throw new Error('Failed to submit feedback');
                }
            } catch (error) {
                console.error('Error submitting feedback:', error);
                showStatus('Failed to submit feedback. Please try again.', 'error');
            }
        }
        
        function showStatus(message, type) {
            const statusDiv = document.getElementById('feedback-status');
            statusDiv.textContent = message;
            statusDiv.style.display = 'block';
            
            if (type === 'success') {
                statusDiv.style.background = '#d4edda';
                statusDiv.style.color = '#155724';
                statusDiv.style.border = '1px solid #c3e6cb';
            } else if (type === 'error') {
                statusDiv.style.background = '#f8d7da';
                statusDiv.style.color = '#721c24';
                statusDiv.style.border = '1px solid #f5c6cb';
            } else {
                statusDiv.style.background = '#d1ecf1';
                statusDiv.style.color = '#0c5460';
                statusDiv.style.border = '1px solid #bee5eb';
            }
        }
        
        // Close feedback overlay when clicking outside
        document.getElementById('feedback-overlay').addEventListener('click', function(e) {
            if (e.target === this) {
                closeFeedback();
            }
        });
        
        // Handle Enter key in textarea (Ctrl+Enter to submit)
        document.getElementById('feedback-text').addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && e.ctrlKey) {
                submitFeedback();
            }
        });
        </script>
        """
        
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
            enhanced_html = self.inject_feedback_interface(html_content)
            
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