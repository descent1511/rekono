from typing import Any

from django.conf import settings
from django.db import models
from security.input_validation import (validate_name, validate_number,
                                       validate_text)
from taggit.managers import TaggableManager

# Create your models here.


class Project(models.Model):
    '''Project model.'''

    name = models.TextField(max_length=100, unique=True, validators=[validate_name])                # Project name
    description = models.TextField(max_length=300, validators=[validate_text])  # Project description
    # Related product Id in Defect-Dojo
    defectdojo_product_id = models.IntegerField(blank=True, null=True, validators=[validate_number])
    # Related engagement Id in Defect-Dojo
    defectdojo_engagement_id = models.IntegerField(blank=True, null=True, validators=[validate_number])
    # Create one engagement in Defect-Dojo for each target
    defectdojo_engagement_by_target = models.BooleanField(default=False)
    # Enable or disable findings synchronization with Defect-Dojo
    defectdojo_synchronization = models.BooleanField(default=False)
    # User that created the project
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)
    # Relation with all users that belong to the project
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='projects', blank=True)
    tags = TaggableManager()                                                    # Project tags

    def __str__(self) -> str:
        '''Instance representation in text format.

        Returns:
            str: String value that identifies this instance
        '''
        return self.name

    def get_project(self) -> Any:
        '''Get the related project for the instance. This will be used for authorization purposes.

        Returns:
            Any: Related project entity
        '''
        return self


class ProjectMembership(models.Model):
    '''Intermediate model for managing user roles within a project.'''

    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('member', 'Member'),
        ('operator', 'Operator'),
    ]

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='memberships'
    )  # Associated project
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='project_memberships'
    )  # Associated user
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='member'
    )  # Role of the user in the project

    class Meta:
        unique_together = ('project', 'user')  # Ensure unique relationship between user and project

    def __str__(self) -> str:
        '''Instance representation in text format.

        Returns:
            str: String value that identifies this instance
        '''
        return f"{self.user.username} ({self.role}) in {self.project.name}"