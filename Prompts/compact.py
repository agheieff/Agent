def get_compact_prompt() -> str:
    """
    Return a specialized instruction prompting the model to summarize
    the conversation's key details, decisions, and next steps.
    """
    return (
        "Please summarize the important details, decisions, actions, and next steps "
        "from the conversation so far in a concise manner. Then, end with a clear "
        "outline of recommended next steps."
    )
