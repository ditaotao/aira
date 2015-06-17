import csv
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import authenticate, login
from django.shortcuts import redirect
from django.http import HttpResponse
from django.core.urlresolvers import reverse
from django.http import Http404
from django.utils.translation import ugettext_lazy as _

from django.views.generic.base import TemplateView
from django.views.generic.edit import CreateView, UpdateView, DeleteView

from django.contrib.auth.models import User
from .models import Profile, Agrifield, IrrigationLog
from .forms import ProfileForm, AgrifieldForm, IrrigationlogForm

from .irma.main import *


class IrrigationPerformance(TemplateView):
    template_name = 'aira/performance-chart.html'

    def get_context_data(self, **kwargs):
        context = super(IrrigationPerformance,
                        self).get_context_data(**kwargs)
        # Load data paths
        daily_r_fps, daily_e_fps, hourly_r_fps, hourly_e_fps = load_meteodata_file_paths()
        f = Agrifield.objects.get(pk=self.kwargs['pk_a'])
        f.can_edit(self.request.user)
        results = performance_chart(f, daily_r_fps, daily_e_fps)
        f.chart_dates = results.chart_dates
        f.chart_ifinal = results.chart_ifinal
        f.applied_water = results.applied_water
        f.sum_ifinal = sum(results.chart_ifinal)
        f.sum_applied_water = sum(results.applied_water)
        f.percentage_diff = _("Not Available")
        if f.sum_ifinal != 0.0:
            f.percentage_diff = round(((f.sum_applied_water - f.sum_ifinal) / f.sum_ifinal)*100 or 0.0)
        context['f'] = f
        return context

def performance_csv(request, pk ):
    f = Agrifield.objects.get(pk=pk)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="{}-performance.csv"'.format(f.name)
    daily_r_fps, daily_e_fps, hourly_r_fps, hourly_e_fps = load_meteodata_file_paths()
    f.can_edit(request.user)
    results = performance_chart(f, daily_r_fps, daily_e_fps)
    writer = csv.writer(response)
    for row in zip(results.chart_dates, results.chart_ifinal, results.applied_water):
            writer.writerow(row)
    return response


class TryPageView(TemplateView):

    def get(self, request):
        user = authenticate(username="demo", password="demo")
        login(request, user)
        return redirect("home", user)


class ConversionTools(TemplateView):
    template_name = 'aira/tools.html'


class IndexPageView(TemplateView):
    template_name = 'aira/index.html'

    def get_context_data(self, **kwargs):
        context = super(IndexPageView, self).get_context_data(**kwargs)
        context['yesterday'] = (timezone.now() - timedelta(days=1)).date()
        daily_r_fps, daily_e_fps, hourly_r_fps, hourly_e_fps = load_meteodata_file_paths()
        arta_rainfall = rasters2point(39.15, 20.98, daily_r_fps)
        arta_evap = rasters2point(39.15, 20.98, daily_e_fps)
        start_data, end_data = common_period_dates(arta_rainfall, arta_evap )
        context['start_date'] = start_data
        context['end_date'] = end_data
        return context


class AlbedoMapsPageView(TemplateView):
    template_name = 'aira/albedo_maps.html'


class HomePageView(TemplateView):
    template_name = 'aira/home.html'

    def get_context_data(self, **kwargs):
        context = super(HomePageView, self).get_context_data(**kwargs)
        # Load data paths
        url_username = kwargs.get('username')
        context['url_username'] = kwargs.get('username')
        if kwargs.get('username') == None:
            url_username = self.request.user
            context['url_username'] = self.request.user
        # User is url_slug <username>
        user = User.objects.get(username=url_username)
        daily_r_fps, daily_e_fps, hourly_r_fps, hourly_e_fps = load_meteodata_file_paths()

	# Fetch models.Profile(User)
        try:
            context['profile'] = Profile.objects.get(farmer=self.request.user)
        except Profile.DoesNotExist:
            context['profile'] = None
        # Fetch models.Agrifield(User)
        try:
            agrifields = Agrifield.objects.filter(owner=user).all()
            for f in agrifields:
		# Check if user is allowed or 404
                f.can_edit(self.request.user)
            # For Profile section
            # Select self.request.user user that set him supervisor
            if Profile.objects.filter(supervisor=self.request.user).exists():
                supervising_users = Profile.objects.filter(
                    supervisor=self.request.user)
                context['supervising_users'] = supervising_users
            context['agrifields'] = agrifields
            context['fields_count'] = len(agrifields)
            for f in agrifields:
       		f.results = model_run(f, "YES",  daily_r_fps, daily_e_fps,
			              hourly_r_fps, hourly_e_fps)
        except Agrifield.DoesNotExist:
            context['agrifields'] = None
        return context


class AdvicePageView(TemplateView):
    template_name = 'aira/advice.html'

    def get_context_data(self, **kwargs):
        context = super(AdvicePageView, self).get_context_data(**kwargs)
        # Load data paths
        daily_r_fps, daily_e_fps, hourly_r_fps, hourly_e_fps = load_meteodata_file_paths()
        Inet_in = "NO"
        f = Agrifield.objects.get(pk=self.kwargs['pk'])
        f.can_edit(self.request.user)
        context['fpars'] = get_parameters(f)
	f.results = model_run(f, "NO", daily_r_fps, daily_e_fps,
		     	          hourly_r_fps, hourly_e_fps)
	context['f'] = f
        return context


# Profile Create/Update
class CreateProfile(CreateView):
    model = Profile
    form_class = ProfileForm
    success_url = "/home"

    def form_valid(self, form):
        form.instance.farmer = self.request.user
        return super(CreateProfile, self).form_valid(form)


class UpdateProfile(UpdateView):
    model = Profile
    form_class = ProfileForm
    success_url = "/home"

    def get_context_data(self, **kwargs):
        context = super(UpdateProfile, self).get_context_data(**kwargs)
        profile = Profile.objects.get(pk=self.kwargs['pk'])
        if not self.request.user == profile.farmer:
            raise Http404
        return context


# Agrifield Create/Update/Delete
class CreateAgrifield(CreateView):
    model = Agrifield
    form_class = AgrifieldForm

    def form_valid(self, form):
        user = User.objects.get(username=self.kwargs['username'])
        form.instance.owner = user
        return super(CreateAgrifield, self).form_valid(form)

    def get_success_url(self):
        url_username = self.kwargs['username']
        return reverse('home', kwargs={'username': url_username})

    def get_context_data(self, **kwargs):
        context = super(CreateAgrifield, self).get_context_data(**kwargs)
        try:
            url_username = self.kwargs['username']
            user = User.objects.get(username=url_username)
            context['agrifields'] = Agrifield.objects.filter(
                owner=user).all()
            context['fields_count'] = context['agrifields'].count()
            context['agrifield_user'] = user

        except Agrifield.DoesNotExist:
            context['agrifields'] = None
        return context


# IrrigationLog Create/Update/Delete
class UpdateAgrifield(UpdateView):
    model = Agrifield
    form_class = AgrifieldForm
    template_name = 'aira/agrifield_update.html'

    def get_success_url(self):
        field = Agrifield.objects.get(pk=self.kwargs['pk'])
        return reverse('home', kwargs={'username': field.owner})

    def get_context_data(self, **kwargs):
        context = super(UpdateAgrifield, self).get_context_data(**kwargs)
        afieldobj = Agrifield.objects.get(pk=self.kwargs['pk'])
        afieldobj.can_edit(self.request.user)
        context['agrifield_user'] = afieldobj.owner
        if agripoint_in_raster(afieldobj):
            context['default_parms'] = get_default_db_value(afieldobj)
        return context


class DeleteAgrifield(DeleteView):
    model = Agrifield
    form_class = AgrifieldForm

    def get_success_url(self):
        field = Agrifield.objects.get(pk=self.kwargs['pk'])
        return reverse('home', kwargs={'username': field.owner})

    def get_context_data(self, **kwargs):
        context = super(DeleteAgrifield, self).get_context_data(**kwargs)
        afieldobj = Agrifield.objects.get(pk=self.kwargs['pk'])
        afieldobj.can_edit(self.request.user)
        return context


class CreateIrrigationLog(CreateView):
    model = IrrigationLog
    form_class = IrrigationlogForm
    success_url = "/home"

    def get_success_url(self):
        field = Agrifield.objects.get(pk=self.kwargs['pk'])
        return reverse('home', kwargs={'username': field.owner})

    def form_valid(self, form):
        form.instance.agrifield = Agrifield.objects.get(pk=self.kwargs['pk'])
        return super(CreateIrrigationLog, self).form_valid(form)

    def get_context_data(self, **kwargs):
        context = super(CreateIrrigationLog, self).get_context_data(**kwargs)
        try:
            context['agrifield'] = Agrifield.objects.get(pk=self.kwargs['pk'])
            afieldobj = Agrifield.objects.get(pk=self.kwargs['pk'])
            afieldobj.can_edit(self.request.user)
            context['logs'] = IrrigationLog.objects.filter(
                agrifield=afieldobj).all()
            context['logs_count'] = context['logs'].count()
            context['agrifield_user'] = afieldobj.owner
        except Agrifield.DoesNotExist:
            context['logs'] = None
        return context


class UpdateIrrigationLog(UpdateView):
    model = IrrigationLog
    form_class = IrrigationlogForm
    template_name = 'aira/irrigationlog_update.html'

    def get_success_url(self):
        field = Agrifield.objects.get(pk=self.kwargs['pk_a'])
        return reverse('home', kwargs={'username': field.owner})

    def get_context_data(self, **kwargs):
        context = super(UpdateIrrigationLog, self).get_context_data(**kwargs)
        afieldobj = Agrifield.objects.get(pk=self.kwargs['pk_a'])
        afieldobj.can_edit(self.request.user)
        log = IrrigationLog.objects.get(pk=self.kwargs['pk'])
        log.can_edit(afieldobj)
        context['agrifield_id'] = afieldobj.id
        return context


class DeleteIrrigationLog(DeleteView):
    model = IrrigationLog
    form_class = IrrigationlogForm

    def get_success_url(self):
        field = Agrifield.objects.get(pk=self.kwargs['pk_a'])
        return reverse('home', kwargs={'username': field.owner})
