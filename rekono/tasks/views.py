from typing import Any
import logging
import os
from django.http import FileResponse
from io import BytesIO
from reportlab.pdfgen import canvas
import reportlab.lib.pagesizes as letter
import reportlab.lib.units as inch
from api.views import CreateViewSet, CreateWithUserViewSet, GetViewSet
from django.core.exceptions import ValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import (CreateModelMixin, DestroyModelMixin,
                                   ListModelMixin, RetrieveModelMixin)
from rest_framework.request import Request
from rest_framework.response import Response

from tasks import services
from tasks.enums import Status
from tasks.filters import TaskFilter
from tasks.models import Task
from tasks.queue import producer
from tasks.serializers import TaskSerializer
from executions.models import Execution

# Create your views here.

logger = logging.getLogger() 
class TaskViewSet(
    GetViewSet,
    CreateViewSet,
    CreateWithUserViewSet,
    CreateModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    DestroyModelMixin
):
    '''Task ViewSet that includes: get, retrieve, create amd cancel features.'''

    queryset = Task.objects.all().order_by('-id')
    serializer_class = TaskSerializer
    filterset_class = TaskFilter
    # Fields used to search tasks
    search_fields = ['target__target', 'process__name', 'process__steps__tool__name', 'tool__name']
    members_field = 'target__project__members'
    user_field = 'executor'

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        '''Cancel task.

        Args:
            request (Request): Received HTTP request

        Returns:
            Response: HTTP response
        '''
        instance = self.get_object()
        try:
            services.cancel_task(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ValidationError:
            return Response(status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(request=None, responses={200: TaskSerializer})
    @action(detail=True, methods=['POST'], url_path='repeat', url_name='repeat')
    def repeat_task(self, request: Request, pk: str) -> Response:
        '''Repeat task execution.

        Args:
            request (Request): Received HTTP request
            pk (str): Id of the task to repeat

        Returns:
            Response: HTTP response
        '''
        task = self.get_object()
        if task.status in [Status.REQUESTED, Status.RUNNING]:
            # If task status is requested or running, it can't be repeated
            return Response('Execution is still running', status=status.HTTP_400_BAD_REQUEST)
        # Create a new task from the original one
        new_task = Task.objects.create(
            target=task.target,
            process=task.process,
            tool=task.tool,
            configuration=task.configuration,
            intensity=task.intensity,
            executor=request.user
        )
        new_task.wordlists.set(task.wordlists.all())                            # Add wordlists from original task
        producer(new_task)                                                      # Enqueue new task
        serializer = TaskSerializer(instance=new_task)                          # Return new task data
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={200: 'File'})
    @action(detail=True, methods=['GET'], url_path='report', url_name='report')
    def get_report(self, request: Request, pk: str) -> Response:
        '''
        Retrieve the report of the task and its related executions.

        Args:
            request (Request): HTTP request
            pk (str): Id of the task

        Returns:
            Response: File response with the report or an error message
        '''
        try:
            # Lấy task dựa trên ID
            task = Task.objects.get(pk=pk)
        except Task.DoesNotExist:
            logger.error("Task not found for ID: %s", pk)
            return Response({'detail': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error("Unexpected error when fetching task: %s", str(e))
            return Response({'detail': f"Error fetching task: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Kiểm tra trạng thái của task
        try:
            if task.status in [Status.REQUESTED, Status.RUNNING]:
                logger.warning("Task ID %s is still running", pk)
                return Response('Execution is still running', status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error("Error checking task status for ID %s: %s", pk, str(e))
            return Response({'detail': f"Error checking task status: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Lấy các Execution liên quan đến Task
        try:
            executions = task.executions.all()
        except Exception as e:
            logger.error("Error fetching executions for Task ID %s: %s", pk, str(e))
            return Response({'detail': f"Error fetching executions: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Đường dẫn lưu báo cáo PDF
        report_path = f'reports/{task.id}_executions_report.pdf'
        if not task.report:
            try:
                os.makedirs(os.path.dirname(report_path), exist_ok=True)
            except Exception as e:
                logger.error("Error creating directory for report file: %s", str(e))
                return Response({'detail': f"Error creating directory: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            try:
                # Tạo PDF chứa thông tin các Execution
                c = canvas.Canvas(report_path)
                c.drawString(100, 750, f"Execution Report for Task ID: {task.id}")

                # Vị trí để vẽ nội dung trong PDF
                y = 700

                # Tiêu đề bảng
                c.drawString(100, y, "Execution ID")
                c.drawString(200, y, "Tool Name")
                c.drawString(400, y, "Status")
                y -= 20

                # Ghi dữ liệu từng Execution
                for execution in executions:
                    c.drawString(100, y, str(execution.id))
                    c.drawString(200, y, execution.tool.name if execution.tool else "N/A")
                    c.drawString(400, y, execution.status)
                    y -= 20

                    # Nếu hết chỗ trong trang, tạo trang mới
                    if y < 50:
                        c.showPage()
                        c.setFont("Helvetica", 12)
                        y = 750

                # Lưu PDF
                c.save()

                # Lưu đường dẫn báo cáo vào task
                task.report = report_path
                task.save()
            except Exception as e:
                logger.error("Error creating or saving PDF for Task ID %s: %s", pk, str(e))
                return Response({'detail': f"Error creating or saving PDF: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Đảm bảo file tồn tại trước khi trả về
        try:
            if not os.path.exists(report_path):
                logger.error("Report file not found for Task ID %s", pk)
                return Response({'detail': 'Report file not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error("Error checking existence of report file for Task ID %s: %s", pk, str(e))
            return Response({'detail': f"Error checking report file existence: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Trả về file PDF
        try:
            response = FileResponse(open(report_path, 'rb'), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{os.path.basename(report_path)}"'
            return response
        except Exception as e:
            logger.error("Error opening or returning report file for Task ID %s: %s", pk, str(e))
            return Response({'detail': f"Error opening report file: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
