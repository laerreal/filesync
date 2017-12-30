__all__ = ["Stateful"]

# Decorator for stateful object classes
class Stateful():
    def __init__(self, *attrs):
        self.attrs = attrs

    def __call__(self, klass):
        def get_state(obj):
            return obj.__state

        def set_state(obj, state, attrs = self.attrs):
            for attr in attrs:
                try:
                    val = getattr(obj, attr + state)
                except AttributeError:
                    val = None
                setattr(obj, attr, val)

        klass.state = property(get_state, set_state)
        return klass