"""A workspace that never set its chat settings: the server defaults apply."""


class UnsetChatSettings:
    async def get_answer_formatting(self, workspace_id):
        return None
