function appData() {
    return {
        // UI State
        showCreateForm: false,
        showProjects: false,
        showConfig: false,
        selectedProject: null,
        isCreating: false,
        showSuccess: false,
        showError: false,
        successMessage: '',
        errorMessage: '',

        // Form Data
        projectForm: {
            user_id: '',
            description: '',
            requirements: [''],
            preferences: {
                framework: 'react',
                styling: 'tailwind',
                deployment: 'netlify'
            }
        },

        // Projects Data
        projects: [],
        sessionId: null,
        pendingApprovals: [],
        showApprovalModal: false,
        currentApproval: null,

        // Initialize the app
        init() {
            this.loadProjects();
            this.createSession();
            this.startAutoRefresh();
            this.checkPendingApprovals();
        },

        // Create a user session
        async createSession() {
            try {
                const response = await fetch('/api/user-input/session?user_id=web_user', {
                    method: 'POST'
                });
                const data = await response.json();
                this.sessionId = data.session_id;
            } catch (error) {
                console.error('Failed to create session:', error);
            }
        },

        // Create a new project
        async createProject() {
            if (!this.projectForm.user_id || !this.projectForm.description) {
                this.showErrorMessage('Please fill in all required fields');
                return;
            }

            this.isCreating = true;

            try {
                // Clean up requirements (remove empty ones)
                const cleanRequirements = this.projectForm.requirements.filter(req => req.trim() !== '');

                const projectData = {
                    user_id: this.projectForm.user_id,
                    description: this.projectForm.description,
                    requirements: cleanRequirements,
                    preferences: this.projectForm.preferences
                };

                const headers = {
                    'Content-Type': 'application/json'
                };

                if (this.sessionId) {
                    headers['X-Session-ID'] = this.sessionId;
                }

                const response = await fetch('/api/projects/', {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify(projectData)
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const result = await response.json();
                
                this.showSuccessMessage('Project created successfully! The AI agents are now working on your website.');
                this.resetForm();
                this.showCreateForm = false;
                this.showProjects = true;
                this.loadProjects();

                // Auto-refresh project status
                setTimeout(() => {
                    this.loadProjects();
                }, 2000);

            } catch (error) {
                console.error('Error creating project:', error);
                this.showErrorMessage('Failed to create project. Please try again.');
            } finally {
                this.isCreating = false;
            }
        },

        // Load all projects
        async loadProjects() {
            try {
                const response = await fetch('/api/projects/');
                const data = await response.json();
                this.projects = data.projects || [];
            } catch (error) {
                console.error('Error loading projects:', error);
            }
        },

        // View project details
        async viewProject(projectId) {
            try {
                const response = await fetch(`/api/projects/${projectId}`);
                const project = await response.json();
                this.selectedProject = project;
            } catch (error) {
                console.error('Error loading project details:', error);
                this.showErrorMessage('Failed to load project details');
            }
        },

        // Simulate project progress (for demo)
        async simulateProgress(projectId) {
            try {
                const response = await fetch(`/api/projects/${projectId}/simulate-progress`, {
                    method: 'POST'
                });
                const result = await response.json();
                
                this.showSuccessMessage(`Project progressed to ${result.progress}%`);
                this.loadProjects();
                
                // If viewing this project, update the details
                if (this.selectedProject && this.selectedProject.project_id === projectId) {
                    this.viewProject(projectId);
                }
            } catch (error) {
                console.error('Error simulating progress:', error);
                this.showErrorMessage('Failed to update project progress');
            }
        },

        // Reset the form
        resetForm() {
            this.projectForm = {
                user_id: '',
                description: '',
                requirements: [''],
                preferences: {
                    framework: 'react',
                    styling: 'tailwind',
                    deployment: 'netlify'
                }
            };
        },

        // Get status color classes
        getStatusColor(status) {
            const colors = {
                'planning': 'bg-blue-100 text-blue-800',
                'development': 'bg-yellow-100 text-yellow-800',
                'testing': 'bg-purple-100 text-purple-800',
                'deployment': 'bg-orange-100 text-orange-800',
                'completed': 'bg-green-100 text-green-800',
                'failed': 'bg-red-100 text-red-800'
            };
            return colors[status] || 'bg-gray-100 text-gray-800';
        },

        // Show success message
        showSuccessMessage(message) {
            this.successMessage = message;
            this.showSuccess = true;
            setTimeout(() => {
                this.showSuccess = false;
            }, 5000);
        },

        // Show error message
        showErrorMessage(message) {
            this.errorMessage = message;
            this.showError = true;
            setTimeout(() => {
                this.showError = false;
            }, 5000);
        },

        // Auto-refresh projects every 10 seconds when viewing projects
        startAutoRefresh() {
            setInterval(() => {
                if (this.showProjects) {
                    this.loadProjects();
                }
                this.checkPendingApprovals();
            }, 10000);
        },

        // Check for pending approvals
        async checkPendingApprovals() {
            try {
                const response = await fetch('/api/approvals/pending');
                const data = await response.json();
                this.pendingApprovals = data.pending_approvals || [];
                
                // Show approval modal if there are pending approvals
                if (this.pendingApprovals.length > 0 && !this.showApprovalModal) {
                    this.currentApproval = this.pendingApprovals[0];
                    this.showApprovalModal = true;
                }
            } catch (error) {
                console.error('Error checking pending approvals:', error);
            }
        },

        // Approve a request
        async approveRequest(requestId, approved) {
            try {
                const response = await fetch(`/api/approvals/${requestId}/respond`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ approved })
                });
                
                const result = await response.json();
                
                if (approved) {
                    this.showSuccessMessage(result.message);
                } else {
                    this.showErrorMessage('Request rejected');
                }
                
                // Close modal and refresh
                this.showApprovalModal = false;
                this.currentApproval = null;
                this.loadProjects();
                this.checkPendingApprovals();
                
            } catch (error) {
                console.error('Error responding to approval:', error);
                this.showErrorMessage('Failed to respond to approval request');
            }
        }
    }
}