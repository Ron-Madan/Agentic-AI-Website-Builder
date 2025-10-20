function appData() {
    return {
        // UI State
        showCreateForm: false,
        showProjects: false,
        showConfig: false,
        showPreviewWorkspace: false,
        isCreating: false,
        showSuccess: false,
        showError: false,

        // Messaging
        successMessage: '',
        errorMessage: '',

        // Project context
        selectedProject: null,
        previousProjectSelection: null,
        detailModalWasOpen: false,
        editorInstance: null,
        editorChangeDisposable: null,
        editorContent: '',
        editorLoadError: '',
        editorContentLoading: false,
        codeInitInFlight: false,
        hasUnsavedChanges: false,
        editorLoading: false,
        editorSaving: false,
        workspaceTab: 'preview',
        workspacePreviewUrl: null,
        workspacePreviewLoading: false,
        workspacePreviewError: '',
        workspaceIframeKey: 0,
        workspaceEditorKey: 0,
        assetUploading: false,
        assetFiles: [],
        assetUploadError: '',
        projectAssets: [],
        editorContext: {
            projectId: null,
            description: '',
            versionId: null,
            previewUrl: null,
            assets: []
        },

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

        _loadingMonaco: null,

        resetAssetInput() {
            const input = document.getElementById('workspace-asset-input');
            if (input) {
                input.value = '';
            }
        },

        handleAssetSelection(event) {
            this.assetUploadError = '';
            const files = event.target.files;
            if (!files || files.length === 0) {
                this.assetFiles = [];
                return;
            }

            const accepted = [];
            for (const file of files) {
                if (file.size > 5 * 1024 * 1024) {
                    this.assetUploadError = 'Files must be 5MB or smaller';
                    continue;
                }

                if (!file.type.startsWith('image/')) {
                    this.assetUploadError = 'Only image files are supported';
                    continue;
                }

                accepted.push(file);
            }

            this.assetFiles = accepted;
        },

        async uploadAssets() {
            console.log('[DEBUG] uploadAssets called, projectId:', this.editorContext.projectId, 'files:', this.assetFiles.length);

            if (!this.editorContext.projectId || this.assetFiles.length === 0) {
                this.assetUploadError = 'Select one or more image files first';
                console.error('[DEBUG] Upload failed: no project or no files');
                return;
            }

            this.assetUploading = true;
            this.assetUploadError = '';

            try {
                const formData = new FormData();
                this.assetFiles.forEach(file => {
                    formData.append('files', file);
                });

                const response = await fetch(`/api/projects/${this.editorContext.projectId}/assets`, {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.detail || 'Upload failed');
                }

                const result = await response.json();

                this.showSuccessMessage('Assets uploaded successfully');
                this.assetFiles = [];
                this.resetAssetInput();

                await this.viewProject(this.editorContext.projectId);
                if (this.selectedProject && this.selectedProject.assets) {
                    this.projectAssets = this.selectedProject.assets;
                } else {
                    this.projectAssets = result.uploaded || [];
                }
                this.editorContext.assets = this.projectAssets;
                this.refreshWorkspacePreview(true);
            } catch (error) {
                console.error('Asset upload failed:', error);
                this.assetUploadError = error.message || 'Asset upload failed';
            } finally {
                this.assetUploading = false;
            }
        },

        async deleteAsset(asset) {
            if (!this.editorContext.projectId || !asset || !asset.asset_id) {
                return;
            }

            if (!confirm(`Delete ${asset.filename}?`)) {
                return;
            }

            try {
                const response = await fetch(`/api/projects/${this.editorContext.projectId}/assets/${asset.asset_id}`, {
                    method: 'DELETE'
                });

                if (!response.ok) {
                    throw new Error('Failed to delete asset');
                }

                this.projectAssets = this.projectAssets.filter(a => a.asset_id !== asset.asset_id);
                this.showSuccessMessage('Asset removed');
                await this.viewProject(this.editorContext.projectId);
                if (this.selectedProject && this.selectedProject.assets) {
                    this.projectAssets = this.selectedProject.assets;
                    this.editorContext.assets = this.selectedProject.assets;
                }
                this.refreshWorkspacePreview(true);
            } catch (error) {
                console.error('Failed to delete asset:', error);
                this.showErrorMessage('Failed to delete asset');
            }
        },

        async openPreviewWorkspace(project, initialTab = 'preview') {
            console.log('[DEBUG] openPreviewWorkspace called with:', project, initialTab);

            if (!project || !project.project_id) {
                console.error('[DEBUG] No project or project_id provided');
                this.showErrorMessage('No project selected');
                return;
            }

            this.editorLoading = true;
            this.showPreviewWorkspace = true;
            this.workspaceTab = initialTab;
            this.workspacePreviewLoading = initialTab === 'preview';
            this.workspacePreviewError = '';
            this.workspacePreviewUrl = null;
            this.workspaceIframeKey += 1;
            this.assetFiles = [];
            this.assetUploadError = '';
            this.detailModalWasOpen = !!this.selectedProject;
            this.previousProjectSelection = this.detailModalWasOpen ? this.selectedProject : null;
            this.editorLoadError = '';
            this.editorContentLoading = true;
            this.hasUnsavedChanges = false; // Reset unsaved changes when opening new project

            const initialPreviewUrl = this.getPreviewUrl(project) || project.preview_url || null;

            this.editorContext = {
                projectId: project.project_id,
                description: project.description || '',
                versionId: null,
                previewUrl: initialPreviewUrl,
                assets: project.assets || []
            };

            try {
                // Skip Monaco loading for now since it's disabled
                // await this.ensureMonaco();

                await this.viewProject(project.project_id);
                const latestProject = this.selectedProject || project;
                this.projectAssets = latestProject.assets || [];
                this.editorContext.assets = this.projectAssets;

                const refreshedPreviewUrl = this.getPreviewUrl(latestProject) || latestProject.preview_url || this.editorContext.previewUrl;
                if (refreshedPreviewUrl) {
                    this.editorContext.previewUrl = refreshedPreviewUrl;
                }

                if (!this.editorContext.previewUrl) {
                    const previewUrl = await this.ensureProjectPreview(project.project_id);
                    if (previewUrl) {
                        this.editorContext.previewUrl = previewUrl;
                        await this.viewProject(project.project_id);
                        this.projectAssets = (this.selectedProject && this.selectedProject.assets) ? this.selectedProject.assets : this.projectAssets;
                        this.editorContext.assets = this.projectAssets;
                    }
                }

                this.refreshWorkspacePreview(true);

                const codeLoaded = await this.fetchProjectCode(project.project_id);
                this.$nextTick(() => {
                    if (codeLoaded && this.workspaceTab === 'code') {
                        this.mountMonacoEditor('workspace-editor');
                    }
                });
            } catch (error) {
                console.error('[DEBUG] Failed to open preview workspace:', error);
                this.showErrorMessage('Unable to load project preview: ' + error.message);
                this.closePreviewWorkspace();
            } finally {
                console.log('[DEBUG] openPreviewWorkspace completed');
                this.editorContentLoading = false;
                this.editorLoading = false;
            }
        },

        async fetchProjectCode(projectId, attempt = 0) {
            if (!projectId) {
                this.editorLoadError = 'No project ID provided';
                return false;
            }

            try {
                console.debug(`[fetchProjectCode] Fetching code for project ${projectId}, attempt ${attempt + 1}`);
                const response = await fetch(`/api/projects/${projectId}/code`);

                if (!response.ok) {
                    let detail = 'Failed to load project code';
                    try {
                        const errorData = await response.json();
                        detail = errorData.detail || detail;
                    } catch (_) {
                        // Ignore JSON parse errors
                    }

                    console.debug(`[fetchProjectCode] Response not OK: ${response.status} - ${detail}`);

                    // Handle specific error cases
                    if (response.status === 404) {
                        if (detail.includes('Code has not been generated yet')) {
                            // This is expected for new projects - provide helpful message
                            this.editorLoadError = 'Code is being generated. Please wait for the project to complete development phase.';
                            this.editorContent = '<!-- Code will appear here once the project development is complete -->';
                            this.editorContext.versionId = null;
                            return true; // Return true so editor can show the placeholder
                        } else if (detail.includes('Project not found')) {
                            this.editorLoadError = 'Project not found';
                            return false;
                        } else if (attempt < 3) {
                            // Retry for other 404s (might be temporary)
                            const backoff = 1000 * (attempt + 1);
                            console.debug(`[fetchProjectCode] Retrying in ${backoff}ms...`);
                            await new Promise(resolve => setTimeout(resolve, backoff));
                            return this.fetchProjectCode(projectId, attempt + 1);
                        }
                    }

                    this.editorLoadError = detail;
                    this.editorContext.versionId = null;
                    return false;
                }

                const data = await response.json();
                console.debug(`[fetchProjectCode] Successfully loaded code, length: ${data.html_content?.length || 0}`);

                this.editorLoadError = '';

                // Only update content if user hasn't made unsaved changes
                if (!this.hasUnsavedChanges) {
                    this.editorContent = data.html_content || '<!-- No content available -->';
                    console.log('[DEBUG] Updated editor content from server');
                } else {
                    console.log('[DEBUG] Skipped content update - user has unsaved changes');
                }

                this.editorContext.versionId = data.version_id || null;
                this.editorContext.assets = data.assets || this.editorContext.assets;

                // Update editor content if editor is already mounted
                if (this.editorInstance) {
                    try {
                        this.editorInstance.setValue(this.editorContent);
                        console.debug('[fetchProjectCode] Updated editor content');
                    } catch (error) {
                        console.warn('[fetchProjectCode] Failed to update editor content:', error);
                    }
                }

                return true;
            } catch (error) {
                console.error('Failed to load project code:', error);

                // Retry on network errors
                if (attempt < 2 && (error.name === 'TypeError' || error.message.includes('fetch'))) {
                    const backoff = 1000 * (attempt + 1);
                    console.debug(`[fetchProjectCode] Network error, retrying in ${backoff}ms...`);
                    await new Promise(resolve => setTimeout(resolve, backoff));
                    return this.fetchProjectCode(projectId, attempt + 1);
                }

                this.editorLoadError = error.message || 'Failed to load project code';
                return false;
            }
        },

        async retryLoadEditor() {
            if (!this.editorContext.projectId) {
                return;
            }

            this.editorLoadError = '';
            this.editorContentLoading = true;

            // Also refresh project data to get latest status
            try {
                await this.viewProject(this.editorContext.projectId);
            } catch (error) {
                console.warn('Failed to refresh project data:', error);
            }

            const loaded = await this.fetchProjectCode(this.editorContext.projectId);

            this.editorContentLoading = false;

            if (loaded && this.workspaceTab === 'code') {
                // If we got real code (not placeholder), mount the editor
                if (!this.editorLoadError || !this.editorLoadError.includes('Code will appear here')) {
                    this.$nextTick(() => {
                        this.mountMonacoEditor('workspace-editor');
                        if (this.editorInstance) {
                            this.editorInstance.layout();
                            this.editorInstance.focus();
                        }
                    });
                }
            }
        },

        closePreviewWorkspace() {
            // Cancel any ongoing operations
            this.codeInitInFlight = false;

            // Dispose editor resources
            this.disposeEditor();

            // Reset all workspace state
            this.showPreviewWorkspace = false;
            this.workspaceTab = 'preview';
            this.workspacePreviewUrl = null;
            this.workspacePreviewLoading = false;
            this.workspacePreviewError = '';
            this.workspaceIframeKey = 0;
            this.workspaceEditorKey += 1; // Increment to force re-render if reopened
            this.editorContent = '';
            this.editorLoadError = '';
            this.editorContentLoading = false;
            this.editorLoading = false;
            this.editorSaving = false;
            this.hasUnsavedChanges = false;
            this.assetFiles = [];
            this.assetUploadError = '';
            this.assetUploading = false;
            this.projectAssets = [];

            // Reset editor context
            this.editorContext = {
                projectId: null,
                description: '',
                versionId: null,
                previewUrl: null,
                assets: []
            };

            // Restore previous project selection if needed
            if (this.detailModalWasOpen && this.previousProjectSelection) {
                this.selectedProject = this.previousProjectSelection;
            } else {
                this.selectedProject = null;
            }
            this.detailModalWasOpen = false;
            this.previousProjectSelection = null;

            console.debug('[Workspace] Closed and cleaned up');
        },

        async ensureProjectPreview(projectId) {
            if (!projectId) {
                return null;
            }

            try {
                const response = await fetch(`/api/projects/${projectId}/preview`, {
                    method: 'POST'
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    const message = errorData.detail || 'Failed to start preview';
                    throw new Error(message);
                }

                const data = await response.json();
                return data.preview_url || null;
            } catch (error) {
                console.error('Failed to ensure project preview:', error);
                this.workspacePreviewError = error.message || 'Preview server unavailable';
                this.workspacePreviewLoading = false;
                return null;
            }
        },

        refreshWorkspacePreview(forceReload = false) {
            console.log('[DEBUG] refreshWorkspacePreview called, previewUrl:', this.editorContext.previewUrl, 'forceReload:', forceReload);

            if (!this.editorContext.previewUrl) {
                console.log('[DEBUG] No preview URL available');
                this.workspacePreviewUrl = null;
                this.workspacePreviewLoading = false;
                return;
            }

            const nextUrl = (() => {
                try {
                    const url = new URL(this.editorContext.previewUrl, window.location.origin);
                    url.searchParams.set('apiHost', window.location.origin);

                    if (forceReload || !this.workspacePreviewUrl) {
                        url.searchParams.set('t', Date.now().toString());
                    } else {
                        const existingUrl = new URL(this.workspacePreviewUrl, window.location.origin);
                        const existingToken = existingUrl.searchParams.get('t');
                        if (existingToken) {
                            url.searchParams.set('t', existingToken);
                        }
                    }

                    return url.toString();
                } catch (error) {
                    const separator = this.editorContext.previewUrl.includes('?') ? '&' : '?';
                    let urlWithApi = `${this.editorContext.previewUrl}${separator}apiHost=${encodeURIComponent(window.location.origin)}`;

                    if (forceReload || !this.workspacePreviewUrl) {
                        const tokenSeparator = urlWithApi.includes('?') ? '&' : '?';
                        urlWithApi = `${urlWithApi}${tokenSeparator}t=${Date.now()}`;
                    } else {
                        const tokenMatch = this.workspacePreviewUrl && this.workspacePreviewUrl.match(/[?&]t=(\d+)/);
                        if (tokenMatch) {
                            const tokenSeparator = urlWithApi.includes('?') ? '&' : '?';
                            urlWithApi = `${urlWithApi}${tokenSeparator}t=${tokenMatch[1]}`;
                        }
                    }

                    return urlWithApi;
                }
            })();

            if (forceReload || nextUrl !== this.workspacePreviewUrl) {
                this.workspacePreviewLoading = true;
                this.workspacePreviewError = '';
                this.workspacePreviewUrl = nextUrl;
                this.workspaceIframeKey += 1;
            } else {
                this.workspacePreviewLoading = false;
                this.workspacePreviewError = '';
            }
        },

        handleWorkspaceTab(tab) {
            console.debug('[Workspace] Tab click:', tab, 'current:', this.workspaceTab);

            // Prevent crashes by catching any errors
            try {
                if (this.workspaceTab === tab) {
                    return;
                }

                // Cancel any ongoing code initialization
                if (this.codeInitInFlight) {
                    console.debug('[Workspace] Canceling ongoing code init');
                    this.codeInitInFlight = false;
                }

                // Clean up when leaving code tab
                if (this.workspaceTab === 'code' && tab !== 'code') {
                    if (this.editorInstance) {
                        try {
                            this.editorContent = this.editorInstance.getValue();
                        } catch (error) {
                            console.warn('Failed to snapshot editor content:', error);
                        }
                    }
                    // Always dispose editor when leaving code tab to prevent conflicts
                    this.disposeEditor();
                }

                this.workspaceTab = tab;
                console.debug('[Workspace] Switched tab to', tab);

                // Handle different tabs
                if (tab === 'preview') {
                    if (!this.workspacePreviewUrl) {
                        this.refreshWorkspacePreview(true);
                    } else {
                        this.workspacePreviewLoading = false;
                        this.workspacePreviewError = '';
                    }
                    return;
                }

                if (tab === 'assets') {
                    return;
                }

                if (tab === 'code') {
                    if (!this.editorContext || !this.editorContext.projectId) {
                        this.editorLoadError = 'No project selected or project is still loading.';
                        return;
                    }

                    this.editorLoadError = '';

                    // Only load code if we don't have content or no unsaved changes
                    if (!this.editorContent || (!this.hasUnsavedChanges && this.editorContent.length === 0)) {
                        console.debug('[CodeTab] Loading code from server');
                        this.fetchProjectCode(this.editorContext.projectId).then(loaded => {
                            console.debug('[CodeTab] Code loaded:', loaded);
                        }).catch(error => {
                            console.error('[CodeTab] Failed to load code:', error);
                            this.editorLoadError = 'Failed to load code: ' + error.message;
                        });
                    } else {
                        console.debug('[CodeTab] Preserving existing content (unsaved changes or content exists)');
                        if (this.hasUnsavedChanges) {
                            console.log('[DEBUG] Preserving unsaved changes');
                        }
                    }
                }
            } catch (error) {
                console.error('[Workspace] Tab switch error:', error);
                this.showErrorMessage('Tab switch failed: ' + error.message);
            }
        },

        async _waitForElement(getter, attempts = 10, delayMs = 30) {
            for (let attempt = 0; attempt < attempts; attempt += 1) {
                const element = typeof getter === 'function' ? getter() : document.querySelector(getter);
                if (element) {
                    return element;
                }

                await new Promise(resolve => setTimeout(resolve, delayMs));

                if (this.workspaceTab !== 'code') {
                    break;
                }
            }

            return null;
        },

        async _initializeCodeTab() {
            console.debug('[CodeTab] init start');

            // Prevent multiple simultaneous initializations
            if (this.codeInitInFlight) {
                console.debug('[CodeTab] init skipped (already in flight)');
                return;
            }

            this.codeInitInFlight = true;

            try {
                // Early exit checks
                if (this.workspaceTab !== 'code') {
                    console.debug('[CodeTab] init aborted (tab changed)');
                    return;
                }

                if (!this.editorContext || !this.editorContext.projectId) {
                    this.editorLoadError = 'No project selected.';
                    console.warn('[CodeTab] No project in context');
                    return;
                }

                // Skip Monaco loading since it's temporarily disabled
                // try {
                //     await this.ensureMonaco();
                //     console.debug('[CodeTab] Monaco ensured');
                // } catch (e) {
                //     console.error('[CodeTab] ensureMonaco failed:', e);
                //     this.editorLoadError = 'Editor library failed to load: ' + (e.message || e);
                //     return;
                // }

                // Check if we still need to be on code tab
                if (this.workspaceTab !== 'code') {
                    console.debug('[CodeTab] init aborted (tab changed during Monaco load)');
                    return;
                }

                // Load project code if needed
                let codeLoaded = true;
                if (!this.editorContent || this.editorLoadError) {
                    this.editorContentLoading = true;
                    try {
                        codeLoaded = await this.fetchProjectCode(this.editorContext.projectId);
                        console.debug('[CodeTab] Code loaded:', codeLoaded);
                    } catch (error) {
                        console.error('Failed to fetch project code:', error);
                        codeLoaded = false;
                        this.editorLoadError = 'Failed to load project code: ' + (error.message || error);
                    } finally {
                        this.editorContentLoading = false;
                    }
                }

                // Final checks before mounting
                if (this.workspaceTab !== 'code') {
                    console.debug('[CodeTab] init aborted (tab changed during code load)');
                    return;
                }

                if (!codeLoaded) {
                    console.debug('[CodeTab] Not mounting editor. codeLoaded:', codeLoaded, 'error:', this.editorLoadError);
                    return;
                }

                // Don't mount editor if we're showing a "waiting for code" message
                if (this.editorLoadError && this.editorLoadError.includes('Code will appear here')) {
                    console.debug('[CodeTab] Code not ready yet, showing placeholder message');
                    return;
                }

                // Wait for DOM to be ready
                await new Promise(resolve => {
                    if (document.readyState === 'complete') {
                        resolve();
                    } else {
                        window.addEventListener('load', resolve, { once: true });
                    }
                });

                // Wait for container to be available and visible
                const container = await this._waitForElement(() => {
                    const el = document.getElementById('workspace-editor');
                    return el && el.offsetParent !== null ? el : null; // Check if visible
                }, 20, 100);

                if (!container || this.workspaceTab !== 'code') {
                    console.debug('[CodeTab] editor container missing or tab changed');
                    this.editorLoadError = 'Editor container not available';
                    return;
                }

                // Mount or remount the editor
                try {
                    console.debug('[CodeTab] mounting monaco editor');
                    this.mountMonacoEditor('workspace-editor');

                    if (this.editorInstance) {
                        // Give it a moment to settle, then layout
                        setTimeout(() => {
                            if (this.editorInstance && this.workspaceTab === 'code') {
                                try {
                                    this.editorInstance.layout();
                                    this.editorInstance.focus();
                                    console.debug('[CodeTab] Editor mounted and focused successfully');
                                } catch (err) {
                                    console.warn('[CodeTab] Post-mount layout/focus failed:', err);
                                }
                            }
                        }, 150);
                    } else {
                        this.editorLoadError = 'Failed to create editor instance';
                    }
                } catch (error) {
                    console.error('Failed to mount Monaco editor:', error);
                    this.editorLoadError = 'Code editor failed to initialize: ' + (error.message || error);
                    this.showErrorMessage('Code editor failed to initialize.');
                }

            } catch (error) {
                console.error('Failed to initialize code tab:', error);
                this.editorLoadError = error.message || 'Failed to load code editor';
                this.showErrorMessage('Code editor failed to load.');
            } finally {
                this.codeInitInFlight = false;
                console.debug('[CodeTab] init end');
            }
        },

        workspaceTabActive(tab) {
            return this.workspaceTab === tab;
        },

        openPreviewInNewTab() {
            const baseUrl = this.editorContext.previewUrl || this.workspacePreviewUrl || (this.selectedProject ? this.getPreviewUrl(this.selectedProject) : null);
            if (baseUrl) {
                try {
                    const url = new URL(baseUrl, window.location.origin);
                    url.searchParams.set('apiHost', window.location.origin);
                    window.open(url.toString(), '_blank');
                } catch (error) {
                    const separator = baseUrl.includes('?') ? '&' : '?';
                    window.open(`${baseUrl}${separator}apiHost=${encodeURIComponent(window.location.origin)}`, '_blank');
                }
            } else {
                this.showErrorMessage('Preview not available');
            }
        },

        handleWorkspacePreviewLoad() {
            this.workspacePreviewLoading = false;
            this.workspacePreviewError = '';
        },

        handleWorkspacePreviewError() {
            this.workspacePreviewLoading = false;
            this.workspacePreviewError = 'Preview failed to load. Try saving again or refresh the preview.';
        },

        async ensureMonaco() {
            // TEMPORARILY DISABLED to prevent crashes
            console.debug('[Monaco] Monaco editor temporarily disabled');
            // No-op: we intentionally avoid throwing to keep the textarea editor visible
        },

        mountMonacoEditor(containerId = 'workspace-editor', attempt = 0) {
            // TEMPORARILY DISABLED to prevent crashes
            console.debug('[Monaco] mountMonacoEditor temporarily disabled');
            // No-op: keep textarea active; do not set editorLoadError
        },

        async saveEditorContent() {
            console.log('[DEBUG] saveEditorContent called');

            if (!this.editorContext.projectId) {
                console.error('[DEBUG] No project ID available for saving');
                console.error('[DEBUG] editorContext:', this.editorContext);
                this.showErrorMessage('No project selected - check console for details');
                return;
            }

            console.log('[DEBUG] Project ID:', this.editorContext.projectId);
            console.log('[DEBUG] Editor content length:', this.editorContent?.length);

            this.editorSaving = true;
            this.editorLoadError = '';

            try {
                // Since Monaco is disabled, use the editorContent directly (it's bound to the textarea)
                let updatedContent = this.editorContent || '';
                console.log('[DEBUG] Content to save:', updatedContent.length, 'characters');
                console.log('[DEBUG] Content preview:', updatedContent.substring(0, 100) + '...');

                // If no content, add some default content for testing
                if (!updatedContent.trim()) {
                    updatedContent = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Save</title>
</head>
<body>
    <h1>Save test at ${new Date().toISOString()}</h1>
    <p>This content was saved from the simple text editor.</p>
</body>
</html>`;
                    console.log('[DEBUG] Using default test content');
                }
                const response = await fetch(`/api/projects/${this.editorContext.projectId}/code`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        html_content: updatedContent,
                        message: 'Manual edit via text editor'
                    })
                });

                if (!response.ok) {
                    throw new Error('Failed to save code');
                }

                const result = await response.json();
                this.showSuccessMessage('Code saved successfully');

                // Reset unsaved changes flag
                this.hasUnsavedChanges = false;
                console.log('[DEBUG] Unsaved changes flag reset');

                if (result.preview_url) {
                    this.editorContext.previewUrl = result.preview_url;
                }

                if (result.version_id) {
                    this.editorContext.versionId = result.version_id;
                }

                // Update editor with cleaned/stored content if backend returned it
                if (result.html_content && typeof result.html_content === 'string') {
                    this.editorContent = result.html_content;
                }

                await this.viewProject(this.editorContext.projectId);
                if (this.selectedProject && this.selectedProject.assets) {
                    this.editorContext.assets = this.selectedProject.assets;
                }
                this.refreshWorkspacePreview(true);
                console.log('[DEBUG] Save completed successfully');
            } catch (error) {
                console.error('[DEBUG] Error saving editor content:', error);
                this.showErrorMessage('Failed to save code: ' + error.message);
            } finally {
                this.editorSaving = false;
                console.log('[DEBUG] Save process finished');
            }
        },

        disposeEditor() {
            // Dispose change listener first
            if (this.editorChangeDisposable) {
                try {
                    this.editorChangeDisposable.dispose();
                } catch (error) {
                    console.warn('Failed to dispose editor change handler:', error);
                }
                this.editorChangeDisposable = null;
            }

            // Dispose editor instance
            if (this.editorInstance) {
                try {
                    // Save content before disposing
                    if (this.editorInstance.getValue) {
                        this.editorContent = this.editorInstance.getValue();
                    }

                    // Dispose the editor
                    this.editorInstance.dispose();
                } catch (error) {
                    console.warn('Failed to dispose editor instance:', error);
                }
                this.editorInstance = null;
            }

            // Clear the container to prevent DOM issues
            const container = document.getElementById('workspace-editor');
            if (container) {
                try {
                    container.innerHTML = '';
                } catch (error) {
                    console.warn('Failed to clear editor container:', error);
                }
            }
        },

        // Initialize the app
        init() {
            // Global error diagnostics to surface hidden exceptions
            if (!window.__awbbErrorHookInstalled) {
                window.__awbbErrorHookInstalled = true;
                window.addEventListener('error', (e) => {
                    console.error('[GlobalError]', e?.message || e);

                    // Handle Monaco-related errors specifically
                    if (e?.message && (e.message.includes('monaco') || e.message.includes('vs/editor') || e.message.includes('editor'))) {
                        console.error('[Monaco Error] Detected Monaco-related error, cleaning up editor');
                        try {
                            if (this.editorInstance) {
                                this.disposeEditor();
                            }
                            // Reset Monaco loading state to allow retry
                            this._loadingMonaco = null;
                            // Clear any Monaco-related DOM elements
                            const monacoScript = document.getElementById('monaco-loader');
                            if (monacoScript) {
                                monacoScript.dataset.error = 'true';
                            }
                        } catch (cleanupError) {
                            console.warn('[Monaco Error] Failed to cleanup editor:', cleanupError);
                        }
                        this.editorLoadError = 'Code editor encountered an error. Please try again.';
                        this.showErrorMessage('Code editor error detected. Click "Check for Code" to retry.');
                    }
                });

                window.addEventListener('unhandledrejection', (e) => {
                    console.error('[UnhandledRejection]', e?.reason || e);

                    // Handle Monaco promise rejections
                    if (e?.reason && typeof e.reason === 'string' &&
                        (e.reason.includes('monaco') || e.reason.includes('vs/editor'))) {
                        console.error('[Monaco Rejection] Monaco promise rejection detected');
                        this.editorLoadError = 'Code editor failed to load properly. Please try again.';
                    }
                });
            }
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
                if (project.assets) {
                    this.projectAssets = project.assets;
                }
                if (this.showPreviewWorkspace && project.preview_url) {
                    this.editorContext.previewUrl = project.preview_url;
                }
                if (this.showPreviewWorkspace && project.feedback_session && project.feedback_session.preview_url) {
                    this.editorContext.previewUrl = project.feedback_session.preview_url;
                }
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
                'initializing': 'bg-gray-100 text-gray-800',
                'planning': 'bg-blue-100 text-blue-800',
                'awaiting_approval': 'bg-indigo-100 text-indigo-800',
                'development': 'bg-yellow-100 text-yellow-800',
                'testing': 'bg-purple-100 text-purple-800',
                'feedback': 'bg-cyan-100 text-cyan-800',
                'awaiting_feedback': 'bg-cyan-100 text-cyan-800',
                'deployment': 'bg-orange-100 text-orange-800',
                'awaiting_deployment_approval': 'bg-orange-100 text-orange-800',
                'deployed': 'bg-green-100 text-green-800',
                'completed': 'bg-green-100 text-green-800',
                'failed': 'bg-red-100 text-red-800'
            };
            return colors[status] || 'bg-gray-100 text-gray-800';
        },

        // Get user-friendly status text
        getStatusText(status) {
            const statusTexts = {
                'initializing': 'Initializing',
                'planning': 'Planning',
                'awaiting_approval': 'Awaiting Approval',
                'development': 'Developing',
                'testing': 'Testing',
                'feedback': 'Feedback Phase',
                'awaiting_feedback': 'Awaiting Feedback',
                'deployment': 'Deploying',
                'awaiting_deployment_approval': 'Awaiting Deployment Approval',
                'deployed': 'Deployed',
                'completed': 'Completed',
                'failed': 'Failed'
            };
            return statusTexts[status] || status;
        },

        // Check if project needs user action
        needsUserAction(project) {
            return ['awaiting_approval', 'awaiting_feedback', 'awaiting_deployment_approval'].includes(project.status);
        },

        // Get preview URL for project
        getPreviewUrl(project) {
            if (project.feedback_session && project.feedback_session.preview_url) {
                return project.feedback_session.preview_url;
            }
            if (project.deployment_url) {
                return project.deployment_url;
            }
            if (project.preview_url) {
                return project.preview_url;
            }
            if (project.status === 'awaiting_feedback' || project.current_phase === 'feedback') {
                return `/preview/${project.project_id}`;
            }
            return null;
        },

        // Open preview in new tab
        async openPreview(project) {
            const target = project || this.selectedProject;
            if (!target || !target.project_id) {
                this.showErrorMessage('Preview not available for this project');
                return;
            }

            let previewUrl = this.getPreviewUrl(target) || target.preview_url || null;

            if (!previewUrl) {
                const ensuredUrl = await this.ensureProjectPreview(target.project_id);
                if (ensuredUrl) {
                    previewUrl = ensuredUrl;
                    if (this.showPreviewWorkspace) {
                        this.editorContext.previewUrl = ensuredUrl;
                    }
                }
            }

            if (!previewUrl) {
                this.showErrorMessage('Preview not available for this project');
                return;
            }

            try {
                const url = new URL(previewUrl, window.location.origin);
                url.searchParams.set('apiHost', window.location.origin);
                window.open(url.toString(), '_blank');
            } catch (error) {
                const separator = previewUrl.includes('?') ? '&' : '?';
                window.open(`${previewUrl}${separator}apiHost=${encodeURIComponent(window.location.origin)}`, '_blank');
            }
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

                // Auto-refresh code if we're in the code tab and waiting for code to be generated
                if (this.showPreviewWorkspace &&
                    this.workspaceTab === 'code' &&
                    this.editorLoadError &&
                    this.editorLoadError.includes('Code will appear here') &&
                    this.editorContext.projectId) {

                    console.debug('[AutoRefresh] Checking for code updates...');
                    this.fetchProjectCode(this.editorContext.projectId).then(loaded => {
                        if (loaded && !this.editorLoadError.includes('Code will appear here')) {
                            console.debug('[AutoRefresh] Code is now available, mounting editor');
                            this.$nextTick(() => {
                                if (this.workspaceTab === 'code') {
                                    this.mountMonacoEditor('workspace-editor');
                                }
                            });
                        }
                    }).catch(error => {
                        console.debug('[AutoRefresh] Code check failed:', error);
                    });
                }
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