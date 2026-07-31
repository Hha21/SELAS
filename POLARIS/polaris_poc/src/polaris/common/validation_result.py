"""
Validation Result Data Models and Reporting Utilities.

This module provides comprehensive data models for validation results,
including support for multiple validation contexts, summary reporting,
and human-readable formatting with emojis and clear structure.
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Union
from enum import Enum
from pathlib import Path


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationCategory(Enum):
    """Categories of validation issues."""
    SCHEMA = "schema"
    DEPENDENCY = "dependency"
    SECURITY = "security"
    PERFORMANCE = "performance"
    COMPATIBILITY = "compatibility"
    SYNTAX = "syntax"
    INTERDEPENDENCY = "interdependency"


@dataclass
class ValidationIssue:
    """Represents a single validation issue with context and suggestions."""
    severity: ValidationSeverity
    category: ValidationCategory
    message: str
    config_path: str = ""
    field_path: str = ""
    suggestions: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    related_fields: List[str] = field(default_factory=list)
    
    def format_issue(self, include_path: bool = True, include_suggestions: bool = True) -> str:
        """Format the validation issue as a human-readable string.
        
        Args:
            include_path: Whether to include file and field path information
            include_suggestions: Whether to include suggestions and examples
            
        Returns:
            Formatted issue string
        """
        severity_emoji = {
            ValidationSeverity.ERROR: "❌",
            ValidationSeverity.WARNING: "⚠️",
            ValidationSeverity.INFO: "ℹ️"
        }
        
        category_emoji = {
            ValidationCategory.SCHEMA: "📋",
            ValidationCategory.DEPENDENCY: "🔗",
            ValidationCategory.SECURITY: "🔒",
            ValidationCategory.PERFORMANCE: "⚡",
            ValidationCategory.COMPATIBILITY: "🔄",
            ValidationCategory.SYNTAX: "📝",
            ValidationCategory.INTERDEPENDENCY: "🕸️"
        }
        
        lines = [f"{severity_emoji[self.severity]} {category_emoji[self.category]} {self.message}"]
        
        if include_path:
            if self.config_path and self.field_path:
                lines.append(f"   📍 Location: {self.config_path} → {self.field_path}")
            elif self.config_path:
                lines.append(f"   📍 File: {self.config_path}")
            elif self.field_path:
                lines.append(f"   📍 Path: {self.field_path}")
        
        if self.related_fields:
            lines.append(f"   🔗 Related: {', '.join(self.related_fields)}")
        
        if include_suggestions and self.suggestions:
            lines.append("   💡 Suggestions:")
            for suggestion in self.suggestions:
                lines.append(f"      • {suggestion}")
        
        if include_suggestions and self.examples:
            lines.append("   📝 Examples:")
            for example in self.examples:
                lines.append(f"      • {example}")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert validation issue to dictionary for serialization."""
        return {
            "severity": self.severity.value,
            "category": self.category.value,
            "message": self.message,
            "config_path": self.config_path,
            "field_path": self.field_path,
            "suggestions": self.suggestions,
            "examples": self.examples,
            "related_fields": self.related_fields
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ValidationIssue':
        """Create validation issue from dictionary."""
        return cls(
            severity=ValidationSeverity(data["severity"]),
            category=ValidationCategory(data["category"]),
            message=data["message"],
            config_path=data.get("config_path", ""),
            field_path=data.get("field_path", ""),
            suggestions=data.get("suggestions", []),
            examples=data.get("examples", []),
            related_fields=data.get("related_fields", [])
        )


@dataclass
class ValidationContext:
    """Context information for validation operations."""
    config_type: str = "unknown"
    config_path: str = ""
    schema_path: str = ""
    validation_timestamp: str = ""
    validator_version: str = "1.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary."""
        return asdict(self)


@dataclass
class ValidationSummary:
    """Summary statistics for validation results."""
    total_files: int = 0
    valid_files: int = 0
    files_with_errors: int = 0
    files_with_warnings: int = 0
    total_issues: int = 0
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    
    @property
    def success_rate(self) -> float:
        """Calculate validation success rate."""
        if self.total_files == 0:
            return 0.0
        return self.valid_files / self.total_files
    
    def format_summary(self) -> str:
        """Format summary as human-readable string."""
        lines = []
        
        # Overall status
        if self.error_count == 0:
            lines.append(f"✅ Validation Summary: {self.valid_files}/{self.total_files} files passed")
        else:
            lines.append(f"❌ Validation Summary: {self.files_with_errors}/{self.total_files} files have errors")
        
        # Detailed statistics
        if self.total_issues > 0:
            lines.append(f"📊 Issue Breakdown:")
            if self.error_count > 0:
                lines.append(f"   ❌ Errors: {self.error_count}")
            if self.warning_count > 0:
                lines.append(f"   ⚠️  Warnings: {self.warning_count}")
            if self.info_count > 0:
                lines.append(f"   ℹ️  Suggestions: {self.info_count}")
        
        # Success rate
        success_percentage = self.success_rate * 100
        lines.append(f"📈 Success Rate: {success_percentage:.1f}%")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert summary to dictionary."""
        return asdict(self)


@dataclass
class ValidationResult:
    """Comprehensive validation result with errors, warnings, and suggestions."""
    valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    context: Optional[ValidationContext] = None
    
    def __post_init__(self):
        """Initialize context if not provided."""
        if self.context is None:
            self.context = ValidationContext()
    
    @property
    def errors(self) -> List[ValidationIssue]:
        """Get only error-level issues."""
        return [issue for issue in self.issues if issue.severity == ValidationSeverity.ERROR]
    
    @property
    def warnings(self) -> List[ValidationIssue]:
        """Get only warning-level issues."""
        return [issue for issue in self.issues if issue.severity == ValidationSeverity.WARNING]
    
    @property
    def infos(self) -> List[ValidationIssue]:
        """Get only info-level issues."""
        return [issue for issue in self.issues if issue.severity == ValidationSeverity.INFO]
    
    @property
    def error_count(self) -> int:
        """Get count of error-level issues."""
        return len(self.errors)
    
    @property
    def warning_count(self) -> int:
        """Get count of warning-level issues."""
        return len(self.warnings)
    
    @property
    def info_count(self) -> int:
        """Get count of info-level issues."""
        return len(self.infos)
    
    @property
    def total_issues(self) -> int:
        """Get total count of all issues."""
        return len(self.issues)
    
    def add_issue(self, issue: ValidationIssue) -> None:
        """Add a validation issue to the result.
        
        Args:
            issue: ValidationIssue to add
        """
        self.issues.append(issue)
        # Update valid status if we have errors
        if issue.severity == ValidationSeverity.ERROR:
            self.valid = False
    
    def add_issues(self, issues: List[ValidationIssue]) -> None:
        """Add multiple validation issues to the result.
        
        Args:
            issues: List of ValidationIssue objects to add
        """
        for issue in issues:
            self.add_issue(issue)
    
    def merge(self, other: 'ValidationResult') -> None:
        """Merge another validation result into this one.
        
        Args:
            other: Another ValidationResult to merge
        """
        self.add_issues(other.issues)
        if not other.valid:
            self.valid = False
    
    def filter_by_severity(self, severity: ValidationSeverity) -> List[ValidationIssue]:
        """Filter issues by severity level.
        
        Args:
            severity: Severity level to filter by
            
        Returns:
            List of issues with the specified severity
        """
        return [issue for issue in self.issues if issue.severity == severity]
    
    def filter_by_category(self, category: ValidationCategory) -> List[ValidationIssue]:
        """Filter issues by category.
        
        Args:
            category: Category to filter by
            
        Returns:
            List of issues with the specified category
        """
        return [issue for issue in self.issues if issue.category == category]
    
    def get_issues_by_path(self, config_path: str) -> List[ValidationIssue]:
        """Get issues for a specific configuration file.
        
        Args:
            config_path: Path to filter by
            
        Returns:
            List of issues for the specified path
        """
        return [issue for issue in self.issues if issue.config_path == config_path]
    
    def format_report(
        self,
        include_summary: bool = True,
        include_context: bool = True,
        group_by_severity: bool = True,
        group_by_file: bool = False,
        max_issues_per_severity: Optional[int] = None
    ) -> str:
        """Format validation result as a comprehensive human-readable report.
        
        Args:
            include_summary: Whether to include summary statistics
            include_context: Whether to include validation context
            group_by_severity: Whether to group issues by severity
            group_by_file: Whether to group issues by file
            max_issues_per_severity: Maximum issues to show per severity level
            
        Returns:
            Formatted report string
        """
        if not self.issues:
            return "✅ Configuration validation passed - no issues found"
        
        lines = []
        
        # Header
        if self.valid:
            lines.append("✅ Configuration validation passed with suggestions")
        else:
            lines.append("❌ Configuration validation failed")
        
        # Context information
        if include_context and self.context:
            if self.context.config_path:
                lines.append(f"📁 File: {self.context.config_path}")
            if self.context.config_type != "unknown":
                lines.append(f"🏷️  Type: {self.context.config_type}")
        
        # Summary statistics
        if include_summary:
            lines.append("")
            lines.append("📊 Issue Summary:")
            if self.error_count > 0:
                lines.append(f"   ❌ Errors: {self.error_count}")
            if self.warning_count > 0:
                lines.append(f"   ⚠️  Warnings: {self.warning_count}")
            if self.info_count > 0:
                lines.append(f"   ℹ️  Suggestions: {self.info_count}")
        
        lines.append("")  # Empty line before details
        
        # Group and display issues
        if group_by_file:
            self._format_issues_by_file(lines, max_issues_per_severity)
        elif group_by_severity:
            self._format_issues_by_severity(lines, max_issues_per_severity)
        else:
            # Show all issues in order
            for i, issue in enumerate(self.issues):
                if max_issues_per_severity and i >= max_issues_per_severity:
                    remaining = len(self.issues) - i
                    lines.append(f"... and {remaining} more issues")
                    break
                lines.append(issue.format_issue())
                lines.append("")
        
        return "\n".join(lines)
    
    def _format_issues_by_severity(self, lines: List[str], max_issues: Optional[int]) -> None:
        """Format issues grouped by severity level."""
        for severity in [ValidationSeverity.ERROR, ValidationSeverity.WARNING, ValidationSeverity.INFO]:
            severity_issues = self.filter_by_severity(severity)
            if severity_issues:
                severity_name = severity.value.title()
                lines.append(f"{'='*20} {severity_name}s {'='*20}")
                
                for i, issue in enumerate(severity_issues):
                    if max_issues and i >= max_issues:
                        remaining = len(severity_issues) - i
                        lines.append(f"... and {remaining} more {severity_name.lower()}s")
                        break
                    lines.append(issue.format_issue())
                    lines.append("")
    
    def _format_issues_by_file(self, lines: List[str], max_issues: Optional[int]) -> None:
        """Format issues grouped by configuration file."""
        # Group issues by config path
        files = {}
        for issue in self.issues:
            path = issue.config_path or "Unknown File"
            if path not in files:
                files[path] = []
            files[path].append(issue)
        
        for config_path, file_issues in files.items():
            lines.append(f"📁 {config_path}")
            lines.append("-" * (len(config_path) + 4))
            
            for i, issue in enumerate(file_issues):
                if max_issues and i >= max_issues:
                    remaining = len(file_issues) - i
                    lines.append(f"... and {remaining} more issues in this file")
                    break
                lines.append(issue.format_issue(include_path=False))
                lines.append("")
    
    def format_json_report(self) -> str:
        """Format validation result as JSON for programmatic consumption.
        
        Returns:
            JSON-formatted report string
        """
        report = {
            "valid": self.valid,
            "summary": {
                "total_issues": self.total_issues,
                "error_count": self.error_count,
                "warning_count": self.warning_count,
                "info_count": self.info_count
            },
            "context": self.context.to_dict() if self.context else None,
            "issues": [issue.to_dict() for issue in self.issues]
        }
        
        return json.dumps(report, indent=2)
    
    def save_report(
        self,
        output_path: Union[str, Path],
        format_type: str = "text"
    ) -> None:
        """Save validation report to file.
        
        Args:
            output_path: Path to save the report
            format_type: Format type ('text' or 'json')
        """
        output_path = Path(output_path)
        
        if format_type == "json":
            content = self.format_json_report()
        else:
            content = self.format_report()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert validation result to dictionary for serialization."""
        return {
            "valid": self.valid,
            "issues": [issue.to_dict() for issue in self.issues],
            "context": self.context.to_dict() if self.context else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ValidationResult':
        """Create validation result from dictionary."""
        result = cls(valid=data["valid"])
        
        # Load issues
        for issue_data in data.get("issues", []):
            result.add_issue(ValidationIssue.from_dict(issue_data))
        
        # Load context
        if data.get("context"):
            result.context = ValidationContext(**data["context"])
        
        return result


class MultiFileValidationResult:
    """Validation result for multiple configuration files."""
    
    def __init__(self):
        """Initialize multi-file validation result."""
        self.file_results: Dict[str, ValidationResult] = {}
        self.overall_valid: bool = True
    
    def add_file_result(self, file_path: str, result: ValidationResult) -> None:
        """Add validation result for a specific file.
        
        Args:
            file_path: Path to the configuration file
            result: ValidationResult for the file
        """
        self.file_results[file_path] = result
        if not result.valid:
            self.overall_valid = False
    
    def get_summary(self) -> ValidationSummary:
        """Get summary statistics for all files.
        
        Returns:
            ValidationSummary with aggregated statistics
        """
        summary = ValidationSummary()
        summary.total_files = len(self.file_results)
        
        for result in self.file_results.values():
            if result.valid and result.error_count == 0:
                summary.valid_files += 1
            if result.error_count > 0:
                summary.files_with_errors += 1
            if result.warning_count > 0:
                summary.files_with_warnings += 1
            
            summary.total_issues += result.total_issues
            summary.error_count += result.error_count
            summary.warning_count += result.warning_count
            summary.info_count += result.info_count
        
        return summary
    
    def get_all_issues(self) -> List[ValidationIssue]:
        """Get all issues from all files.
        
        Returns:
            List of all validation issues
        """
        all_issues = []
        for result in self.file_results.values():
            all_issues.extend(result.issues)
        return all_issues
    
    def format_report(
        self,
        include_file_details: bool = True,
        include_summary: bool = True,
        max_issues_per_file: Optional[int] = None
    ) -> str:
        """Format multi-file validation report.
        
        Args:
            include_file_details: Whether to include per-file details
            include_summary: Whether to include overall summary
            max_issues_per_file: Maximum issues to show per file
            
        Returns:
            Formatted report string
        """
        lines = []
        summary = self.get_summary()
        
        # Overall header
        if self.overall_valid:
            lines.append("✅ Multi-file configuration validation completed")
        else:
            lines.append("❌ Multi-file configuration validation found errors")
        
        # Summary
        if include_summary:
            lines.append("")
            lines.append(summary.format_summary())
        
        # Per-file details
        if include_file_details:
            lines.append("")
            lines.append("📋 File Details:")
            lines.append("=" * 50)
            
            for file_path, result in self.file_results.items():
                lines.append("")
                if result.valid and result.error_count == 0:
                    lines.append(f"✅ {file_path}")
                else:
                    lines.append(f"❌ {file_path}")
                
                if result.issues:
                    # Show limited issues per file
                    issues_to_show = result.issues
                    if max_issues_per_file:
                        issues_to_show = result.issues[:max_issues_per_file]
                    
                    for issue in issues_to_show:
                        lines.append(f"   {issue.format_issue(include_path=False)}")
                    
                    if max_issues_per_file and len(result.issues) > max_issues_per_file:
                        remaining = len(result.issues) - max_issues_per_file
                        lines.append(f"   ... and {remaining} more issues")
        
        return "\n".join(lines)
    
    def save_report(
        self,
        output_path: Union[str, Path],
        format_type: str = "text"
    ) -> None:
        """Save multi-file validation report to file.
        
        Args:
            output_path: Path to save the report
            format_type: Format type ('text' or 'json')
        """
        output_path = Path(output_path)
        
        if format_type == "json":
            report_data = {
                "overall_valid": self.overall_valid,
                "summary": self.get_summary().to_dict(),
                "files": {
                    path: result.to_dict() 
                    for path, result in self.file_results.items()
                }
            }
            content = json.dumps(report_data, indent=2)
        else:
            content = self.format_report()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)