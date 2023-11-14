from .NodeInterface import NodeInterface
from .SerialInterface import SerialInterface
from .GenericInterface import GenericInterface
from .DummyInterface import DummyInterface
from typing import Type,Dict

SUPPORTED_INTERFACES: Dict[str, Type[GenericInterface]] = {
        "Node Forwarder": NodeInterface,
        "Direct Serial": SerialInterface
    }

DEBUG_SUPPORTED_INTERFACES: Dict[str, Type[GenericInterface]] = {
        **SUPPORTED_INTERFACES,
        "Dummy Interface": DummyInterface
}

        