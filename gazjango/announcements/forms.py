from django import forms
from announcements.models import Announcement

class SubmitAnnouncementForm(forms.ModelForm):
    text = forms.CharField(widget=forms.Textarea(attrs={'rows': 5, 'cols': 40}))
    is_event = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={'onchange': 'toggleEventFields();'}),
        initial=False,
        required=False
    )
    
    class Meta:
        model = Announcement
        fields  = ('title', 'text', 'date_start', 'date_end', 'sponsor')
        fields += ('sponsor_url', 'event_date', 'event_time', 'event_place')
    
    def clean(self):
        super(SubmitAnnouncementForm, self).clean()
        d = self.cleaned_data
        err = forms.ValidationError
        val = lambda key: d[key] if key in d else None
        
        if val('sponsor_url') and not val('sponsor'):
            raise err("You have to give a sponsor name if you have a sponsor link.")
        if val('is_event') and not val('event_date'):
            raise err("You need to give a date if this is a specific event.")
        
        return d
    