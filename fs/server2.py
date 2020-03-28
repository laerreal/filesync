class Error:
    pass

class NoSuchCommand(Error):
    pass

class HandlerError(Error):
    pass

class HandlerFinished:
    pass
