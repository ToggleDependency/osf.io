import pytest
import mock
from mock import call
import datetime

from osf.management.commands.add_notification_subscription import add_reviews_notification_setting
from osf.management.commands.populate_registration_provider_notification_subscriptions import populate_registration_provider_notification_subscriptions

from osf.migrations import update_provider_auth_groups
from osf.models import NotificationDigest
from osf.models.action import RegistrationAction
from website.profile.utils import get_profile_image_url

from osf_tests.factories import (
    RegistrationFactory,
    AuthUserFactory,
    RetractionFactory
)

from website import mails, settings

from osf.utils.workflows import RegistrationModerationTriggers, RegistrationModerationStates

from osf.utils.notifications import (
    notify_submit,
    notify_accept_reject,
    notify_moderator_registration_requests_withdrawal,
    notify_reject_withdraw_request,
    notify_withdraw_registration
)

@pytest.mark.django_db
class TestRegistrationMachineNotification:

    MOCK_NOW = datetime.datetime(2018, 2, 4)

    @pytest.yield_fixture(autouse=True)
    def setup(self):
        populate_registration_provider_notification_subscriptions()
        with mock.patch('osf.utils.machines.timezone.now', return_value=self.MOCK_NOW):
            yield

    @pytest.fixture()
    def contrib(self):
        return AuthUserFactory()

    @pytest.fixture()
    def admin(self):
        return AuthUserFactory()

    @pytest.fixture()
    def registration(self, admin, contrib):
        registration = RegistrationFactory(creator=admin)
        registration.add_contributor(admin, 'admin')
        registration.add_contributor(contrib, 'write')
        update_provider_auth_groups()
        return registration

    @pytest.fixture()
    def registration_with_retraction(self, admin, contrib):
        sanction = RetractionFactory(user=admin)
        registration = sanction.target_registration
        registration.update_moderation_state()
        registration.add_contributor(admin, 'admin')
        registration.add_contributor(contrib, 'write')
        registration.save()
        return registration

    @pytest.fixture()
    def provider(self, registration):
        return registration.provider

    @pytest.fixture()
    def moderator(self, provider):
        user = AuthUserFactory()
        provider.add_to_group(user, 'moderator')
        return user

    @pytest.fixture()
    def accept_action(self, registration, admin):
        registration_action = RegistrationAction.objects.create(
            creator=admin,
            target=registration,
            trigger=RegistrationModerationTriggers.ACCEPT_SUBMISSION.db_name,
            from_state=RegistrationModerationStates.INITIAL.db_name,
            to_state=RegistrationModerationStates.ACCEPTED.db_name,
            comment='yo'
        )
        return registration_action

    @pytest.fixture()
    def withdraw_request_action(self, registration, admin):
        registration_action = RegistrationAction.objects.create(
            creator=admin,
            target=registration,
            trigger=RegistrationModerationTriggers.REQUEST_WITHDRAWAL.db_name,
            from_state=RegistrationModerationStates.ACCEPTED.db_name,
            to_state=RegistrationModerationStates.PENDING_WITHDRAW.db_name,
            comment='yo'
        )
        return registration_action

    @pytest.fixture()
    def withdraw_action(self, registration, admin):
        registration_action = RegistrationAction.objects.create(
            creator=admin,
            target=registration,
            trigger=RegistrationModerationTriggers.ACCEPT_WITHDRAWAL.db_name,
            from_state=RegistrationModerationStates.PENDING_WITHDRAW.db_name,
            to_state=RegistrationModerationStates.WITHDRAWN.db_name,
            comment='yo'
        )
        return registration_action

    def test_submit_notifications(self, registration, moderator, admin, contrib, provider):
        """
        [REQS-96] "As moderator of branded registry, I receive email notification upon admin author(s) submission approval"
        :param mock_email:
        :param draft_registration:
        :return:
        """

        with mock.patch('website.reviews.listeners.mails.send_mail') as mock_send_mail:
            notify_submit(registration, admin)

        assert len(mock_send_mail.call_args_list) == 2
        admin_message, contrib_message = mock_send_mail.call_args_list

        assert admin_message == call(
            admin.email,
            mails.REVIEWS_SUBMISSION_CONFIRMATION,
            document_type='registration',
            domain='http://localhost:5000/',
            is_creator=True,
            logo='osf_registries',
            mimetype='html',
            no_future_emails=[],
            provider_contact_email=settings.OSF_CONTACT_EMAIL,
            provider_support_email=settings.OSF_SUPPORT_EMAIL,
            provider_name=provider.name,
            provider_url='http://localhost:5000/',
            referrer=admin,
            reviewable=registration,
            user=admin,
            workflow=None
        )

        assert contrib_message == call(
            contrib.email,
            mails.REVIEWS_SUBMISSION_CONFIRMATION,
            document_type='registration',
            domain='http://localhost:5000/',
            is_creator=False,
            logo='osf_registries',
            mimetype='html',
            no_future_emails=[],
            provider_contact_email=settings.OSF_CONTACT_EMAIL,
            provider_support_email=settings.OSF_SUPPORT_EMAIL,
            provider_name=provider.name,
            provider_url='http://localhost:5000/',
            referrer=admin,
            reviewable=registration,
            user=contrib,
            workflow=None
        )

        assert NotificationDigest.objects.count() == 1
        digest = NotificationDigest.objects.last()

        assert digest.user == moderator
        assert digest.send_type == 'email_transactional'
        assert digest.event == 'new_pending_submissions'

    def test_accept_notifications(self, registration, moderator, admin, contrib, accept_action):
        """
        [REQS-98] "As registration authors, we receive email notification upon moderator acceptance"
        :param draft_registration:
        :return:
        """
        add_reviews_notification_setting('global_reviews')

        with mock.patch('website.notifications.emails.store_emails') as mock_email:
            notify_accept_reject(registration, registration.creator, accept_action, RegistrationModerationStates)

        assert len(mock_email.call_args_list) == 2

        admin_message, contrib_message = mock_email.call_args_list

        assert admin_message == call(
            [admin._id],
            'email_transactional',
            'global_reviews',
            admin,
            registration,
            self.MOCK_NOW,
            comment='yo',
            document_type='registration',
            domain='http://localhost:5000/',
            has_psyarxiv_chronos_text=False,
            is_creator=True,
            is_rejected=False,
            notify_comment='yo',
            provider_contact_email=settings.OSF_CONTACT_EMAIL,
            provider_support_email=settings.OSF_SUPPORT_EMAIL,
            provider_url='http://localhost:5000/',
            requester=admin,
            reviewable=registration,
            template='reviews_submission_status',
            was_pending=False,
            workflow=None
        )

        assert contrib_message == call(
            [contrib._id],
            'email_transactional',
            'global_reviews',
            admin,
            registration,
            self.MOCK_NOW,
            comment='yo',
            document_type='registration',
            domain='http://localhost:5000/',
            has_psyarxiv_chronos_text=False,
            is_creator=False,
            is_rejected=False,
            notify_comment='yo',
            provider_contact_email=settings.OSF_CONTACT_EMAIL,
            provider_support_email=settings.OSF_SUPPORT_EMAIL,
            provider_url='http://localhost:5000/',
            reviewable=registration,
            requester=admin,
            template='reviews_submission_status',
            was_pending=False,
            workflow=None
        )

    def test_reject_notifications(self, registration, moderator, admin, contrib, accept_action):
        """
        [REQS-100] "As authors of rejected by moderator registration, we receive email notification of registration returned
        to draft state"
        :param draft_registration:
        :return:
        """
        add_reviews_notification_setting('global_reviews')

        with mock.patch('website.notifications.emails.store_emails') as mock_email:
            notify_accept_reject(registration, registration.creator, accept_action, RegistrationModerationStates)

        assert len(mock_email.call_args_list) == 2

        admin_message, contrib_message = mock_email.call_args_list

        assert admin_message == call(
            [admin._id],
            'email_transactional',
            'global_reviews',
            admin,
            registration,
            self.MOCK_NOW,
            comment='yo',
            document_type='registration',
            domain='http://localhost:5000/',
            has_psyarxiv_chronos_text=False,
            is_creator=True,
            is_rejected=False,
            notify_comment='yo',
            provider_contact_email=settings.OSF_CONTACT_EMAIL,
            provider_support_email=settings.OSF_SUPPORT_EMAIL,
            provider_url='http://localhost:5000/',
            reviewable=registration,
            requester=admin,
            template='reviews_submission_status',
            was_pending=False,
            workflow=None
        )

        assert contrib_message == call(
            [contrib._id],
            'email_transactional',
            'global_reviews',
            admin,
            registration,
            self.MOCK_NOW,
            comment='yo',
            document_type='registration',
            domain='http://localhost:5000/',
            has_psyarxiv_chronos_text=False,
            is_creator=False,
            is_rejected=False,
            notify_comment='yo',
            provider_contact_email=settings.OSF_CONTACT_EMAIL,
            provider_support_email=settings.OSF_SUPPORT_EMAIL,
            provider_url='http://localhost:5000/',
            reviewable=registration,
            requester=admin,
            template='reviews_submission_status',
            was_pending=False,
            workflow=None
        )

    def test_notify_moderator_registration_requests_withdrawal_notifications(self, registration, contrib, admin, moderator, provider):
        """
         [REQS-106] "As moderator, I receive registration withdrawal request notification email"

        :param mock_email:
        :param draft_registration:
        :param contrib:
        :return:
        """

        with mock.patch('website.notifications.emails.store_emails') as mock_email:
            notify_moderator_registration_requests_withdrawal(registration, admin)

        assert len(mock_email.call_args_list) == 1

        transactional = mock_email.call_args_list[0]

        assert transactional == call(
            [moderator._id],
            'email_transactional',
            'new_pending_withdraw_requests',
            admin,
            registration,
            self.MOCK_NOW,
            abstract_provider=registration.provider,
            document_type='registration',
            domain='http://localhost:5000/',
            message=f'submitted "{registration.title}".',
            profile_image_url=get_profile_image_url(admin),
            provider_contact_email=settings.OSF_CONTACT_EMAIL,
            provider_support_email=settings.OSF_SUPPORT_EMAIL,
            provider_url='http://localhost:5000/',
            referrer=admin,
            reviewable=registration,
            reviews_submission_url=f'http://localhost:5000/reviews/registries/osf/{registration._id}',
            workflow=None
        )

    def test_withdrawal_registration_accepted_notifications(self, registration_with_retraction, contrib, admin, withdraw_action):
        """
        [REQS-109] "As registration author(s) requesting registration withdrawal, we receive notification email of moderator
        decision"

        :param mock_email:
        :param draft_registration:
        :param contrib:
        :return:
        """

        with mock.patch('osf.utils.machines.mails.send_mail') as mock_email:
            notify_withdraw_registration(registration_with_retraction, withdraw_action)

        assert len(mock_email.call_args_list) == 2
        admin_message, contrib_message = mock_email.call_args_list

        assert admin_message == call(
            admin.email,
            mails.WITHDRAWAL_REQUEST_GRANTED,
            contributor=admin,
            document_type='registration',
            domain='http://localhost:5000/',
            is_requester=True,
            force_withdrawal=False,
            provider_contact_email=settings.OSF_CONTACT_EMAIL,
            provider_support_email=settings.OSF_SUPPORT_EMAIL,
            provider_url='http://localhost:5000/',
            requester=admin,
            reviewable=registration_with_retraction,
            workflow=None
        )

        assert contrib_message == call(
            contrib.email,
            mails.WITHDRAWAL_REQUEST_GRANTED,
            contributor=contrib,
            document_type='registration',
            domain='http://localhost:5000/',
            is_requester=False,
            force_withdrawal=False,
            provider_contact_email=settings.OSF_CONTACT_EMAIL,
            provider_support_email=settings.OSF_SUPPORT_EMAIL,
            provider_url='http://localhost:5000/',
            requester=admin,
            reviewable=registration_with_retraction,
            workflow=None
        )

    def test_withdrawal_registration_rejected_notifications(self, registration, contrib, admin, withdraw_request_action):
        """
        [REQS-109] "As registration author(s) requesting registration withdrawal, we receive notification email of moderator
        decision"

        :param mock_email:
        :param draft_registration:
        :param contrib:
        :return:
        """

        with mock.patch('osf.utils.machines.mails.send_mail') as mock_email:
            notify_reject_withdraw_request(registration, withdraw_request_action)

        assert len(mock_email.call_args_list) == 2
        admin_message, contrib_message = mock_email.call_args_list

        assert admin_message == call(
            admin.email,
            mails.WITHDRAWAL_REQUEST_DECLINED,
            contributor=admin,
            document_type='registration',
            domain='http://localhost:5000/',
            is_requester=True,
            provider_contact_email=settings.OSF_CONTACT_EMAIL,
            provider_support_email=settings.OSF_SUPPORT_EMAIL,
            provider_url='http://localhost:5000/',
            requester=admin,
            reviewable=registration,
            workflow=None
        )

        assert contrib_message == call(
            contrib.email,
            mails.WITHDRAWAL_REQUEST_DECLINED,
            contributor=contrib,
            document_type='registration',
            domain='http://localhost:5000/',
            is_requester=False,
            provider_contact_email=settings.OSF_CONTACT_EMAIL,
            provider_support_email=settings.OSF_SUPPORT_EMAIL,
            provider_url='http://localhost:5000/',
            requester=admin,
            reviewable=registration,
            workflow=None
        )

    def test_withdrawal_registration_force_notifications(self, registration_with_retraction, contrib, admin, withdraw_action):
        """
        [REQS-109] "As registration author(s) requesting registration withdrawal, we receive notification email of moderator
        decision"

        :param mock_email:
        :param draft_registration:
        :param contrib:
        :return:
        """

        with mock.patch('osf.utils.machines.mails.send_mail') as mock_email:
            notify_withdraw_registration(registration_with_retraction, withdraw_action)

        assert len(mock_email.call_args_list) == 2
        admin_message, contrib_message = mock_email.call_args_list

        assert admin_message == call(
            admin.email,
            mails.WITHDRAWAL_REQUEST_GRANTED,
            contributor=admin,
            document_type='registration',
            domain='http://localhost:5000/',
            is_requester=True,
            force_withdrawal=False,
            provider_contact_email=settings.OSF_CONTACT_EMAIL,
            provider_support_email=settings.OSF_SUPPORT_EMAIL,
            provider_url='http://localhost:5000/',
            requester=admin,
            reviewable=registration_with_retraction,
            workflow=None
        )

        assert contrib_message == call(
            contrib.email,
            mails.WITHDRAWAL_REQUEST_GRANTED,
            contributor=contrib,
            document_type='registration',
            domain='http://localhost:5000/',
            is_requester=False,
            force_withdrawal=False,
            provider_contact_email=settings.OSF_CONTACT_EMAIL,
            provider_support_email=settings.OSF_SUPPORT_EMAIL,
            provider_url='http://localhost:5000/',
            requester=admin,
            reviewable=registration_with_retraction,
            workflow=None
        )
