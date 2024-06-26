from .NodeInterface import NodeInterface, DummyNodeInterface
from .SerialInterface import SerialInterface
from .GenericInterface import GenericInterface
from .DummyInterface import DummyInterface

SUPPORTED_INTERFACES: dict[str, type[GenericInterface]] = {
        "Direct Serial": SerialInterface,
        "Node Forwarder": NodeInterface
    }

DEBUG_SUPPORTED_INTERFACES: dict[str, type[GenericInterface]] = {
        **SUPPORTED_INTERFACES,
        "Dummy Interface": DummyInterface,
        "Dummy Node Forwarder": DummyNodeInterface
}

     