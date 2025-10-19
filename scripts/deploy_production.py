#!/usr/bin/env python3
"""Production deployment script for Agentic Web App Builder."""

import os
import sys
import argparse
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agentic_web_app_builder.core.production_config import (
    ProductionConfigManager, 
    DeploymentEnvironment,
    get_production_config_manager
)
from agentic_web_app_builder.core.system_monitoring import get_system_monitoring_manager


logger = logging.getLogger(__name__)


class ProductionDeployer:
    """Handles production deployment of the Agentic Web App Builder."""
    
    def __init__(self):
        """Initialize the production deployer."""
        self.config_manager = get_production_config_manager()
        self.monitoring_manager = get_system_monitoring_manager()
        self.project_root = Path(__file__).parent.parent
    
    def deploy(self, 
               environment: str = "production",
               config_file: Optional[str] = None,
               output_dir: str = "./deployment",
               validate_only: bool = False,
               skip_docker: bool = False,
               skip_k8s: bool = False) -> bool:
        """Deploy the application to production."""
        try:
            logger.info(f"Starting production deployment for environment: {environment}")
            
            # Load configuration
            if config_file:
                config = self.config_manager.load_from_file(config_file)
            else:
                config = self.config_manager.load_from_environment()
            
            # Override environment if specified
            if environment:
                config.environment = DeploymentEnvironment(environment)
            
            # Validate configuration
            validation_errors = self.config_manager.validate_configuration(config)
            if validation_errors:
                logger.error("Configuration validation failed:")
                for error in validation_errors:
                    logger.error(f"  - {error}")
                return False
            
            logger.info("Configuration validation passed")
            
            if validate_only:
                logger.info("Validation-only mode, skipping deployment")
                return True
            
            # Create output directory
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Generate deployment files
            logger.info("Generating deployment files")
            self.config_manager.save_configuration(output_dir, config)
            
            # Generate additional deployment scripts
            self._generate_deployment_scripts(output_path, config)
            
            # Build Docker image (if not skipped)
            if not skip_docker:
                logger.info("Building Docker image")
                if not self._build_docker_image(output_path, config):
                    logger.error("Docker image build failed")
                    return False
            
            # Generate Kubernetes manifests (if not skipped)
            if not skip_k8s:
                logger.info("Kubernetes manifests generated")
                # K8s manifests are already generated in save_configuration
            
            # Initialize monitoring
            logger.info("Initializing monitoring configuration")
            self._setup_monitoring(config)
            
            logger.info(f"Production deployment completed successfully")
            logger.info(f"Deployment files saved to: {output_path.absolute()}")
            
            # Print next steps
            self._print_next_steps(output_path, config)
            
            return True
            
        except Exception as e:
            logger.error(f"Production deployment failed: {str(e)}")
            return False
    
    def _generate_deployment_scripts(self, output_path: Path, config) -> None:
        """Generate additional deployment scripts."""
        
        # Generate start script
        start_script = f"""#!/bin/bash
# Start script for Agentic Web App Builder

set -e

echo "Starting Agentic Web App Builder..."

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

# Check required environment variables
required_vars=("SECRET_KEY" "JWT_SECRET_KEY" "DATABASE_URL")
for var in "${{required_vars[@]}}"; do
    if [ -z "${{!var}}" ]; then
        echo "Error: Required environment variable $var is not set"
        exit 1
    fi
done

# Start the application
exec python -m uvicorn src.agentic_web_app_builder.api.main:app \\
    --host {config.host} \\
    --port {config.port} \\
    --workers {config.scaling.max_workers} \\
    --access-log \\
    --log-level {config.logging.level.lower()}
"""
        
        (output_path / "start.sh").write_text(start_script)
        (output_path / "start.sh").chmod(0o755)
        
        # Generate health check script
        health_check_script = f"""#!/bin/bash
# Health check script for Agentic Web App Builder

curl -f http://localhost:{config.port}/health || exit 1
"""
        
        (output_path / "health_check.sh").write_text(health_check_script)
        (output_path / "health_check.sh").chmod(0o755)
        
        # Generate backup script
        backup_script = f"""#!/bin/bash
# Backup script for Agentic Web App Builder

set -e

BACKUP_DIR="/backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "Creating backup in $BACKUP_DIR"

# Backup database
if [ "$DATABASE_TYPE" = "postgresql" ]; then
    pg_dump "$DATABASE_URL" > "$BACKUP_DIR/database.sql"
elif [ "$DATABASE_TYPE" = "sqlite" ]; then
    cp "$DATABASE_NAME.db" "$BACKUP_DIR/database.db"
fi

# Backup configuration
cp .env "$BACKUP_DIR/" 2>/dev/null || true
cp config.json "$BACKUP_DIR/" 2>/dev/null || true

# Backup logs
cp -r logs "$BACKUP_DIR/" 2>/dev/null || true

echo "Backup completed: $BACKUP_DIR"
"""
        
        (output_path / "backup.sh").write_text(backup_script)
        (output_path / "backup.sh").chmod(0o755)
        
        # Generate monitoring setup script
        monitoring_script = f"""#!/bin/bash
# Monitoring setup script

set -e

echo "Setting up monitoring..."

# Create monitoring directories
mkdir -p /var/log/agentic-web-app-builder
mkdir -p /var/lib/prometheus
mkdir -p /var/lib/grafana

# Set permissions
chown -R 1000:1000 /var/lib/prometheus
chown -R 472:472 /var/lib/grafana

# Generate Prometheus configuration
cat > prometheus.yml << EOF
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'agentic-web-app-builder'
    static_configs:
      - targets: ['localhost:{config.port}']
    metrics_path: '/metrics'
    scrape_interval: 30s

  - job_name: 'system'
    static_configs:
      - targets: ['localhost:{config.monitoring.metrics_port}']
    scrape_interval: 30s
EOF

echo "Monitoring setup completed"
"""
        
        (output_path / "setup_monitoring.sh").write_text(monitoring_script)
        (output_path / "setup_monitoring.sh").chmod(0o755)
    
    def _build_docker_image(self, output_path: Path, config) -> bool:
        """Build Docker image."""
        try:
            # Copy Dockerfile to project root if it doesn't exist
            dockerfile_path = self.project_root / "Dockerfile"
            if not dockerfile_path.exists():
                dockerfile_content = self.config_manager.generate_dockerfile(config)
                dockerfile_path.write_text(dockerfile_content)
            
            # Build Docker image
            image_name = f"agentic-web-app-builder:{config.app_version}"
            
            cmd = [
                "docker", "build",
                "-t", image_name,
                "-f", str(dockerfile_path),
                str(self.project_root)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Docker build failed: {result.stderr}")
                return False
            
            logger.info(f"Docker image built successfully: {image_name}")
            
            # Save image info
            image_info = {
                "image_name": image_name,
                "build_time": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
                "version": config.app_version,
                "environment": config.environment.value
            }
            
            import json
            (output_path / "image_info.json").write_text(json.dumps(image_info, indent=2))
            
            return True
            
        except Exception as e:
            logger.error(f"Docker build error: {str(e)}")
            return False
    
    def _setup_monitoring(self, config) -> None:
        """Setup monitoring configuration."""
        try:
            self.monitoring_manager.initialize(
                log_level=config.logging.level,
                enable_json_logging=config.logging.enable_json_logging,
                log_file=config.logging.file_path,
                enable_metrics=config.monitoring.enable_metrics,
                metrics_port=config.monitoring.metrics_port,
                enable_sentry=bool(config.sentry_dsn),
                sentry_dsn=config.sentry_dsn,
                environment=config.environment.value
            )
            
            logger.info("Monitoring configuration initialized")
            
        except Exception as e:
            logger.warning(f"Failed to initialize monitoring: {str(e)}")
    
    def _print_next_steps(self, output_path: Path, config) -> None:
        """Print next steps for deployment."""
        print("\n" + "="*60)
        print("DEPLOYMENT COMPLETED SUCCESSFULLY")
        print("="*60)
        print(f"\nDeployment files generated in: {output_path.absolute()}")
        print(f"Environment: {config.environment.value}")
        print(f"Application version: {config.app_version}")
        
        print("\nNext Steps:")
        print("1. Review the generated configuration files:")
        print(f"   - {output_path}/config.json")
        print(f"   - {output_path}/.env.template")
        print(f"   - {output_path}/docker-compose.yml")
        
        print("\n2. Set up environment variables:")
        print(f"   cp {output_path}/.env.template .env")
        print("   # Edit .env with your actual values")
        
        print("\n3. Deploy using Docker Compose:")
        print(f"   cd {output_path}")
        print("   docker-compose up -d")
        
        print("\n4. Or deploy to Kubernetes:")
        print(f"   kubectl apply -f {output_path}/k8s/")
        
        print("\n5. Monitor the deployment:")
        print(f"   # Health check: curl http://localhost:{config.port}/health")
        print(f"   # Metrics: http://localhost:{config.monitoring.metrics_port}/metrics")
        print("   # Logs: docker-compose logs -f app")
        
        if config.monitoring.enable_metrics:
            print(f"\n6. Access monitoring dashboards:")
            print(f"   # Prometheus: http://localhost:{config.monitoring.metrics_port}")
            print("   # Grafana: http://localhost:3000 (admin/admin)")
        
        print("\n7. Backup and maintenance:")
        print(f"   # Create backup: {output_path}/backup.sh")
        print(f"   # Health check: {output_path}/health_check.sh")
        
        print("\n" + "="*60)


def main():
    """Main deployment function."""
    parser = argparse.ArgumentParser(description="Deploy Agentic Web App Builder to production")
    
    parser.add_argument(
        "--environment", "-e",
        choices=["development", "staging", "production"],
        default="production",
        help="Deployment environment"
    )
    
    parser.add_argument(
        "--config-file", "-c",
        help="Configuration file path"
    )
    
    parser.add_argument(
        "--output-dir", "-o",
        default="./deployment",
        help="Output directory for deployment files"
    )
    
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate configuration, don't deploy"
    )
    
    parser.add_argument(
        "--skip-docker",
        action="store_true",
        help="Skip Docker image building"
    )
    
    parser.add_argument(
        "--skip-k8s",
        action="store_true",
        help="Skip Kubernetes manifest generation"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create deployer and run deployment
    deployer = ProductionDeployer()
    
    success = deployer.deploy(
        environment=args.environment,
        config_file=args.config_file,
        output_dir=args.output_dir,
        validate_only=args.validate_only,
        skip_docker=args.skip_docker,
        skip_k8s=args.skip_k8s
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()