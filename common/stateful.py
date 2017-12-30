__all__ = ["Stateful"]

class Stateful():
    """Decorator for stateful object classes"""
    def __init__(self, *attrs):
        self.attrs = attrs

    def __call__(self, klass):
        def getState(obj):
            return obj.__state

        def setState(obj, state, attrs = self.attrs):
            obj.__state = state

            for attr in attrs:
                try:
                    val = getattr(obj, attr + state)
                except AttributeError:
                    try:
                        delattr(obj, attr)
                    except AttributeError:
                        pass
                else:
                    setattr(obj, attr, val)

        klass.state = property(getState, setState)
        return klass
