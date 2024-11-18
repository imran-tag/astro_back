# portal/views.py
from django.shortcuts import render, redirect
from django.views import View
from django.contrib import messages
from .services.api_service import AstroAPIService
from datetime import datetime
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
import os
from django.conf import settings
from django.urls import reverse
import time


INTERVENTION_STEPS = [
    'security_checklist',
    'photo_upload',  # current step
    'photos_after',
    # ... other steps
]

class LoginView(View):
    template_name = 'portal/login.html'

    def get(self, request):
        if 'token' in request.session:
            return redirect('interventions')
        return render(request, self.template_name)

    def post(self, request):
        email = request.POST.get('email')
        password = request.POST.get('password')

        api_service = AstroAPIService()
        response = api_service.login(email, password)

        if response and response.get('success'):
            request.session['token'] = response['token']
            request.session['user'] = {
                'uid': response['uid'],
                'email': response['email'],
                'firstname': response['firstname'],
                'lastname': response['lastname']
            }
            return redirect('interventions')
        else:
            messages.error(request, response.get('message', 'Login failed'))
            return render(request, self.template_name)


class InterventionListView(View):
    template_name = 'portal/interventions/list.html'

    def get(self, request):
        print("DEBUG: Accessing list view")

        if 'token' not in request.session or 'user' not in request.session:
            return redirect('login')


        api_service = AstroAPIService()
        token = request.session['token']
        user_uid = request.session['user']['uid']

        # Get filter from query params, default to 'all'
        filter_type = request.GET.get('filter', 'all')

        interventions = api_service.get_interventions(token, user_uid, page=1)

        if interventions:
            print("DEBUG: Available intervention IDs:", [i.get('uid') for i in interventions])
            # Group interventions by date
            grouped_interventions = {}
            today = timezone.now().date()

            for intervention in interventions:
                # Convert the date string to a datetime object
                try:
                    # Assuming date_time is in format 'dd/mm/yyyy'
                    intervention_date = datetime.strptime(
                        intervention['date_time'],
                        '%d/%m/%Y'
                    ).date()

                    # Filter based on status if needed
                    if filter_type == 'planned' and intervention['status_uid'] != 'planifiee':
                        continue
                    elif filter_type == 'in_progress' and intervention['status_uid'] != 'en_cours':
                        continue

                    # Add to grouped dictionary
                    if intervention_date not in grouped_interventions:
                        grouped_interventions[intervention_date] = []
                    grouped_interventions[intervention_date].append(intervention)

                except ValueError as e:
                    print(f"Error parsing date: {e}")
                    continue

            # Sort interventions within each date group by time
            for date in grouped_interventions:
                grouped_interventions[date].sort(
                    key=lambda x: x.get('time_from', '')
                )

            # Sort dates and create final sorted dictionary
            sorted_dates = sorted(grouped_interventions.keys())
            sorted_interventions = {}

            # Add today's interventions first if they exist
            if today in grouped_interventions:
                sorted_interventions['today'] = grouped_interventions[today]

            # Add remaining dates
            for date in sorted_dates:
                if date != today:
                    sorted_interventions[date] = grouped_interventions[date]
        else:
            sorted_interventions = {}

        context = {
            'grouped_interventions': sorted_interventions,
            'today': today,
            'current_filter': filter_type
        }

        return render(request, self.template_name, context)


# portal/views.py
class InterventionDetailView(View):
    template_name = 'portal/interventions/detail.html'

    def get(self, request, intervention_id):
        print(f"DEBUG: Accessing detail view for intervention {intervention_id}")

        if 'token' not in request.session or 'user' not in request.session:
            return redirect('login')

        api_service = AstroAPIService()
        token = request.session['token']
        user_uid = request.session['user']['uid']

        # Get all interventions and find the specific one
        all_interventions = api_service.get_interventions(token, user_uid, page=1)

        if all_interventions:
            # Find the specific intervention
            intervention = next(
                (i for i in all_interventions if str(i.get('uid')) == str(intervention_id)),
                None
            )

            if intervention:
                return render(request, self.template_name, {
                    'intervention': intervention
                })

        messages.error(request, 'Intervention non trouvée')
        return redirect('interventions')


# portal/views.py
@method_decorator(csrf_exempt, name='dispatch')
class InterventionUpdateStatusView(View):
    def post(self, request, intervention_id):
        if 'token' not in request.session:
            return JsonResponse({'success': False, 'message': 'Not authenticated'}, status=401)

        try:
            # No need to parse request body anymore since we're always setting to 'en_cours'
            api_service = AstroAPIService()
            result = api_service.update_intervention_status(
                request.session['token'],
                intervention_id,
                'en_cours'  # Status is hardcoded since we're always setting to 'en_cours'
            )

            if result:
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False, 'message': 'Failed to update status'})

        except Exception as e:
            print(f"Error updating status: {str(e)}")
            return JsonResponse({'success': False, 'message': str(e)}, status=500)


class SecurityChecklistView(View):
    template_name = 'portal/interventions/security_checklist.html'

    def get(self, request, intervention_id):
        if 'token' not in request.session or 'user' not in request.session:
            return redirect('login')

        api_service = AstroAPIService()
        token = request.session['token']
        user_uid = request.session['user']['uid']

        # Get all interventions and find the specific one
        all_interventions = api_service.get_interventions(token, user_uid, page=1)

        if all_interventions:
            intervention = next(
                (i for i in all_interventions if str(i.get('uid')) == str(intervention_id)),
                None
            )

            if intervention:
                # Check if status_uid is 5 (En cours)
                if intervention.get('status_uid') == '5':
                    return render(request, self.template_name, {
                        'intervention': intervention
                    })
                else:
                    messages.error(request, 'Cette intervention n\'est pas en cours')
                    return redirect('intervention_detail', intervention_id=intervention_id)

        messages.error(request, 'Intervention non trouvée')
        return redirect('interventions')
        current_step_index = INTERVENTION_STEPS.index('security_checklist')
        next_step = INTERVENTION_STEPS[current_step_index + 1]
        next_url = reverse(next_step, kwargs={'intervention_id': intervention_id})

        return render(request, self.template_name, {
            'intervention': intervention,
            'next_url': next_url
        })


@method_decorator(csrf_exempt, name='dispatch')
class PhotoUploadView(View):
    template_name = 'portal/interventions/photo_upload.html'

    def get(self, request, intervention_id):
        if 'token' not in request.session or 'user' not in request.session:
            return redirect('login')

        api_service = AstroAPIService()
        token = request.session['token']
        user_uid = request.session['user']['uid']

        all_interventions = api_service.get_interventions(token, user_uid, page=1)

        if all_interventions:
            intervention = next(
                (i for i in all_interventions if str(i.get('uid')) == str(intervention_id)),
                None
            )

            if intervention:
                return render(request, self.template_name, {
                    'intervention': intervention,
                    'intervention_images': intervention.get('images_before', ''),
                })

        messages.error(request, 'Intervention non trouvée')
        return redirect('interventions')

    def post(self, request, intervention_id):
        if 'token' not in request.session:
            return JsonResponse({'code': '0', 'message': 'error2'})

        if 'file' not in request.FILES:
            return JsonResponse({'code': '2', 'message': 'no record'})

        api_service = AstroAPIService()
        token = request.session['token']
        user_uid = request.session['user']['uid']

        # Get current intervention data
        all_interventions = api_service.get_interventions(token, user_uid, page=1)
        current_intervention = next(
            (i for i in all_interventions if str(i.get('uid')) == str(intervention_id)),
            None
        )

        if not current_intervention:
            return JsonResponse({'code': '0', 'message': 'Intervention not found'})

        # Upload file
        upload_response = api_service.upload_media(
            token,
            request.FILES['file'],
            intervention_id,
            current_intervention
        )

        if not upload_response or upload_response.get('code') != '1':
            return JsonResponse({'code': '0', 'message': 'Upload failed'})

        # Get current images and append new one
        current_images = current_intervention.get('images_before', '')
        new_image_path = upload_response.get('file_path', '')

        if current_images:
            updated_images = f"{current_images},{new_image_path}"
        else:
            updated_images = new_image_path

        # Update intervention with new images
        update_response = api_service.update_intervention_images(
            token,
            intervention_id,
            updated_images,
            current_intervention
        )

        if update_response and update_response.get('code') == 1:
            return JsonResponse(upload_response)
        else:
            return JsonResponse({'code': '0', 'message': 'Failed to update intervention'})


@method_decorator(csrf_exempt, name='dispatch')
class PhotosAfterView(View):
    template_name = 'portal/interventions/photos_after.html'

    def get(self, request, intervention_id):
        if 'token' not in request.session or 'user' not in request.session:
            return redirect('login')

        api_service = AstroAPIService()
        token = request.session['token']
        user_uid = request.session['user']['uid']

        all_interventions = api_service.get_interventions(token, user_uid, page=1)

        if all_interventions:
            intervention = next(
                (i for i in all_interventions if str(i.get('uid')) == str(intervention_id)),
                None
            )

            if intervention:
                current_step_index = INTERVENTION_STEPS.index('photos_after')
                next_step = INTERVENTION_STEPS[current_step_index + 1] if current_step_index + 1 < len(
                    INTERVENTION_STEPS) else None
                next_url = reverse(next_step, kwargs={'intervention_id': intervention_id}) if next_step else None

                return render(request, self.template_name, {
                    'intervention': intervention,
                    'intervention_images': intervention.get('images_after', ''),
                    'next_url': next_url
                })

        messages.error(request, 'Intervention non trouvée')
        return redirect('interventions')

    def post(self, request, intervention_id):
        if 'token' not in request.session:
            return JsonResponse({'code': '0', 'message': 'error2'})

        if 'file' not in request.FILES:
            return JsonResponse({'code': '2', 'message': 'no record'})

        api_service = AstroAPIService()
        token = request.session['token']
        user_uid = request.session['user']['uid']

        # Get current intervention data
        all_interventions = api_service.get_interventions(token, user_uid, page=1)
        current_intervention = next(
            (i for i in all_interventions if str(i.get('uid')) == str(intervention_id)),
            None
        )

        if not current_intervention:
            return JsonResponse({'code': '0', 'message': 'Intervention not found'})

        # Upload file
        upload_response = api_service.upload_media(
            token,
            request.FILES['file'],
            intervention_id,
            current_intervention
        )

        if not upload_response or upload_response.get('code') != '1':
            return JsonResponse({'code': '0', 'message': 'Upload failed'})

        # Get current images and append new one
        current_images = current_intervention.get('images_after', '')
        new_image_path = upload_response.get('file_path', '')

        if current_images:
            updated_images = f"{current_images},{new_image_path}"
        else:
            updated_images = new_image_path

        # Update intervention with new images
        update_response = api_service.update_intervention_images_after(
            token,
            intervention_id,
            updated_images,
            current_intervention
        )

        if update_response and update_response.get('code') == 1:
            return JsonResponse(upload_response)
        else:
            return JsonResponse({'code': '0', 'message': 'Failed to update intervention'})

class LogoutView(View):
    def get(self, request):
        request.session.flush()
        return redirect('login')