import pytest

from polaris_refactored.src.infrastructure.di import DIContainer, Injectable


def test_singleton_and_transient_and_factory_with_deps():
    c = DIContainer()

    class A(Injectable):
        def __init__(self):
            self.val = 1

    class B(Injectable):
        def __init__(self, a: A):
            self.a = a

    # Singleton A
    c.register_singleton(A, A)
    # Factory for B uses dependency A
    c.register_factory(B, lambda: B(c.resolve(A)))

    a1 = c.resolve(A)
    a2 = c.resolve(A)
    assert a1 is a2

    b1 = c.resolve(B)
    b2 = c.resolve(B)
    # default factory returns singleton unless registered as transient
    assert b1 is c.resolve(B)
    assert b1.a is a1

    # Transient registration
    class C(Injectable):
        def __init__(self):
            pass

    c.register_transient(C, C)
    c1 = c.resolve(C)
    c2 = c.resolve(C)
    assert c1 is not c2


def test_missing_dependency_error_message():
    c = DIContainer()

    class Y(Injectable):
        pass

    class X(Injectable):
        def __init__(self, not_registered: Y):
            self.n = not_registered

    with pytest.raises(ValueError) as ex:
        c.register_singleton(X, X)
        c.resolve(X)
    assert "Cannot resolve dependency" in str(ex.value) or "is not registered" in str(ex.value)


def test_clear_resets_registrations():
    c = DIContainer()

    class A(Injectable):
        pass

    c.register_singleton(A, A)
    assert c.resolve(A) is c.resolve(A)
    c.clear()
    with pytest.raises(ValueError):
        c.resolve(A)
