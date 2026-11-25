"""Django admin never deletes CharityOS records.

Records with history are archived (owner decision 4.1). Permanently erasing
an account is a separate, deliberate operation: the dry-run-first
``manage.py erase_user`` command (decision 4.3). Turning off the delete
permission removes the delete view, the delete button and the
"delete selected" action, for superusers too.
"""


class NoHardDeleteAdmin:
    def has_delete_permission(self, request, obj=None):
        return False
