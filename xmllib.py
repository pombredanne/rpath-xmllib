#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


"""
The rPath XML Library API.

All interfaces in this modules that do not start with a C{_}
character are public interfaces.
"""

import os
import sys
import StringIO
from xml import sax

from lxml import etree
import collections

#{ Exception classes
class XmlLibError(Exception):
    "Top-level exception class"

class UndefinedNamespaceError(XmlLibError):
    "Raised when a reference to an undefined namespace is found"

class InvalidXML(XmlLibError):
    "Raised when the XML data is invalid"

class SchemaValidationError(XmlLibError):
    "Raised when the XML data is not validating against the XML schema"

class UnknownSchemaError(SchemaValidationError):
    """
    Raised when an unknown or missing schema was specified in the XML document
    """

#}

#{ Base classes
class SerializableObject(object):
    """
    Base class for an XML-serializable object
    """

    __slots__ = ()

    # pylint: disable-msg=R0903
    # Too few public methods (1/2): this is an interface
    def getElementTree(self, parent = None):
        """Any serializable object should implement the C{getElementTree}
        method, which returns a hierarchy of objects that represent the
        structure of the XML document.

        @param parent: An optional parent object.
        @type parent: C{SerializableObject} instance
        """
        name = self._getName()

        attrs = {}
        for attrName, attrVal in self._iterAttributes():
            if isinstance(attrVal, bool):
                attrVal = BooleanNode.toString(attrVal)
            elif not isinstance(attrVal, (str, unicode)):
                attrVal = str(attrVal)
            attrs[attrName] = attrVal

        localNamespaces = self._getLocalNamespaces()

        elem = createElementTree(name, attrs, localNamespaces, parent = parent)
        for child in self._iterChildren():
            if hasattr(child, 'getElementTree'):
                child.getElementTree(parent = elem)
            elif isinstance(child, (str, unicode)):
                elem.text = child
        return elem

    def _getName(self):
        """
        @return: the node's XML tag
        @rtype: C{str}
        """
        raise NotImplementedError()

    def _getLocalNamespaces(self):
        """
        @return: the locally defined namespaces
        @rtype: C{dict}
        """
        raise NotImplementedError()

    def _iterAttributes(self):
        """
        Iterate over this node's attributes.
        @return: iteratable of (attributeName, attributeValue)
        @rtype: iterable of (attributeName, attributeValue) strings
        """
        raise NotImplementedError()

    def _iterChildren(self):
        """
        Iterate over the node's children
        """
        raise NotImplementedError()

class _AbstractNode(SerializableObject):
    """Abstract node class for parsing XML data"""
    __slots__ = ('_children', '_nsMap', '_name', '_nsAttributes',
                 '_otherAttributes', )

    def __init__(self, attributes = None, nsMap = None, name = None):
        SerializableObject.__init__(self)
        self._name = (None, name)
        self._children = []
        self._nsMap = nsMap or {}
        self._nsAttributes = {}
        self._otherAttributes = {}
        self._setAttributes(attributes)
        if name is not None:
            self.setName(name)

    def setName(self, name):
        """Set the node's name"""
        nsName, tagName = splitNamespace(name)
        if nsName is not None and nsName not in self._nsMap:
            raise UndefinedNamespaceError(nsName)
        self._name = (nsName, tagName)
        return self

    def getName(self):
        """
        @return: the node's name
        @rtype: C{str}
        """
        return unsplitNamespace(self._name[1], self._name[0])

    def getAbsoluteName(self):
        """
        Retrieve the node's absolute name (qualified with the full
        namespace), in the format C{{namespace}node}
        @return: the node's absolute name
        @rtype: C{str}
        """
        if self._name[0] is None and None not in self._nsMap:
            # No default namespace provided
            return self._name[1]
        return "{%s}%s" % (self._nsMap[self._name[0]], self._name[1])

    def addChild(self, childNode):
        """
        Add a child node to this node
        @param childNode: Child node to be added to this node
        @type childNode: Node
        """
        # If the previous node in the list is character data, drop it, since
        # we don't support mixed content
        if self._children and isinstance(self._children[-1], unicode):
            self._children[-1] = childNode.finalize()
        else:
            if childNode.getName() in getattr(self, '_singleChildren', []):
                setattr(self, childNode.getName(), childNode.finalize())
            else:
                self._children.append(childNode.finalize())

    def iterChildren(self):
        "Iterate over this node's children"
        if hasattr(self, '_childOrder'):
            # pylint: disable-msg=E1101
            # no '_childOrder' member: we just tested for that
            return orderItems(self._children, self._childOrder)
        return iter(self._children)

    def finalize(self):
        "Post-process this node (e.g. cast text to the expected type)"
        return self

    def characters(self, ch):
        """Add character data to this node.
        @param ch: Character data to be added
        @type ch: C{str}
        @return: self
        @rtype: C{type(self)}
        """
        if self._children:
            if isinstance(self._children[-1], unicode):
                self._children[-1] += ch
            # We don't support mixed contents, so don't bother adding
            # characters after children
        else:
            self._children.append(ch)
        return self

    def getNamespaceMap(self):
        "Return a copy of the namespace mapping"
        return self._nsMap.copy()

    def iterAttributes(self):
        """
        Iterate over this node's attributes.
        @return: iterable of (attributeName, attributeValue)
        @rtype: iterable of (attributeName, attributeValue) strings
        """
        for nsName, nsVal in sorted(self._nsAttributes.items()):
            if nsName is None:
                yield ('xmlns', nsVal)
            else:
                yield ('xmlns:%s' % nsName, nsVal)
        for (nsName, attrName), attrVal in self._otherAttributes.items():
            if nsName is None:
                yield (attrName, attrVal)
            else:
                yield ("%s:%s" % (nsName, attrName), attrVal)

    def iterNamespaces(self):
        """
        Iterate over this node's namespaces
        @return: iterable of (namespaceAlias, namespaceValue), with a
        C{namespaceAlias} equal to {None} for the default namespace.
        @rtype: iterable of (namespaceAlias, namespaceValue) strings
        """
        for nsName, nsVal in sorted(self._nsAttributes.items()):
            yield nsName, nsVal

    def getAttribute(self, name, namespace = None):
        """
        Get an attribute's value.
        @param name: the attribute name
        @type name: C{str}
        @param namespace: the namespace alias for the attribute (or None for
        the attribute with this name from the default namespace).
        @type namespace: C{str} or C{None}
        @return: the attribute's value
        @rtype: C{str}
        """
        return self._otherAttributes.get((namespace, name))

    def getAttributeByNamespace(self, name, namespace = None):
        """
        Retrieve an attribute using its full namespace designation
        @param name: the attribute name
        @type name: C{str}
        @param namespace: the full namespace for the attribute. Passing
        C{None} is equivalent to calling C{getAttribute} with the name and no
        namespace, i.e. the node's attribute will be returned only if no
        default namespace is set.
        @type namespace: C{str} or C{None}
        @return: the attribute's value
        @rtype: C{str}
        """
        if namespace is None:
            # Nothing different from getAttribute
            return self.getAttribute(name)

        # Get all aliases that correspond to this namespace
        aliases = [ x for (x, y) in self._nsMap.items() if y == namespace ]
        # Sort them (this way the default namespace comes first)
        aliases.sort()
        for alias in aliases:
            if (alias, name) in self._otherAttributes:
                return self._otherAttributes[(alias, name)]
        return None

    def getChildren(self, name, namespace = None):
        """
        Get a node's children, by name and (the optional) namespace.
        @param name: the attribute name
        @type name: C{str}
        @param namespace: the namespace alias for the attribute (or None for
        the attribute with this name from the default namespace).
        @type namespace: C{str} or C{None}
        @return: The children nodes with the specified name.
        @rtype: C{list}
        """
        tagName = unsplitNamespace(name, namespace)
        return [ x for x in self.iterChildren()
            if hasattr(x, 'getName') and x.getName() == tagName ]

    def getText(self):
        "Return a node's character data"
        text = [ x for x in self._children if isinstance(x, (str, unicode)) ]
        if not text:
            return ''
        return text[0]

    #{ Methods for serializing Node objects
    # pylint: disable-msg=C0111
    # docstring inherited from parent class
    def _getName(self):
        if self._name[0] is None:
            return self._name[1]
        return "{%s}%s" % (self._nsMap[self._name[0]], self._name[1])

    # pylint: disable-msg=C0111
    # docstring inherited from parent class
    def _getLocalNamespaces(self):
        return self._nsAttributes

    # pylint: disable-msg=C0111
    # docstring inherited from parent class
    def _iterAttributes(self):
        for (nsName, attrName), attrVal in self._otherAttributes.items():
            attrName = self._buildElementTreeName(attrName, nsName)
            yield (attrName, attrVal)

    # pylint: disable-msg=C0111
    # docstring inherited from parent class
    def _iterChildren(self):
        return self.iterChildren()
    #}

    #{ Private methods
    def _setAttributes(self, attributes):
        "Set a node's attributes"
        self._nsAttributes = {}
        self._otherAttributes = {}
        if attributes is None:
            return
        nonNsAttr = []
        for attrName, attrVal in attributes.items():
            arr = attrName.split(':', 1)
            if arr[0] != 'xmlns':
                # Copy the tag aside, we may need to qualify it later
                if len(arr) == 1:
                    # No name space specified, use default
                    attrKey = (None, attrName)
                else:
                    attrKey = tuple(arr)
                nonNsAttr.append((attrKey, attrVal))
                continue
            if len(arr) == 1:
                nsName = None
            else:
                nsName = arr[1]
            self._nsMap[nsName] = attrVal
            self._nsAttributes[nsName] = attrVal
        # Now walk all attributes and qualify them with the namespace if
        # necessary
        for (nsName, attrName), attrVal in nonNsAttr:
            if nsName == 'xml' and nsName not in self._nsMap:
                # Bare xml: with no xmlns:xml specification
                # Reading http://www.w3.org/TR/xmlbase/#syntax
                # we'll assume that an undefined xml namespace prefix is
                # bound to DataBinder.xmlBaseNamespace
                self._nsMap[nsName] = self._nsAttributes[nsName] = DataBinder.xmlBaseNamespace
            if nsName is not None and nsName not in self._nsMap:
                raise UndefinedNamespaceError(nsName)
            self._otherAttributes[(nsName, attrName)] = attrVal

    def _buildElementTreeName(self, name, namespace = None):
        "Convenience function for building a namespace-qualified node name"
        if namespace is None:
            return name
        return "{%s}%s" % (self._nsMap[namespace], name)
    #}

class BaseNode(_AbstractNode):
    """Base node for parsing XML data"""

    __slots__ = ()
#}

#{ Specialized nodes
class GenericNode(BaseNode):
    """
    Base node for all data classes used by SAX handler. Neither this class,
    nor any descendent needs to be instantiated. They should be registered
    with instances of the DataBinder class.

    This class serves as the base datatype. This is the default node type
    if nothing else is specified, thus it's not useful to register this
    class.

    By default, _addChild will add the childNode to a list. specifying an
    attribute in _singleChildren will cause the value to be stored directly.
    """

    __slots__ = ()

class IntegerNode(BaseNode):
    """
    Integer data class for SAX parser.

    Registering a tag with this class will render the text contents into
    an integer when finalize is called. All attributes and tags will be lost.
    If no text is set, this object will default to 0.
    """

    __slots__ = ()

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('name', 'int')
        BaseNode.__init__(self, *args, **kwargs)

    def finalize(self):
        "Convert the character data to an integer"
        text = self.getText()
        try:
            return int(text)
        except ValueError:
            return 0

    # pylint: disable-msg=C0111
    # docstring inherited from parent class
    def _iterChildren(self):
        yield str(self.finalize())

class StringNode(BaseNode):
    """
    String data class for SAX parser.

    Registering a tag with this class will render the text contents into
    a string when finalize is called. All attributes and tags will be lost.
    If no text is set, this object will default to ''.
    """

    __slots__ = ()

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('name', 'string')
        BaseNode.__init__(self, *args, **kwargs)

    def finalize(self):
        "Convert the text data to a string"
        text = self.getText()
        return text

    # pylint: disable-msg=C0111
    # docstring inherited from parent class
    def _iterChildren(self):
        yield self.finalize()

class NullNode(BaseNode):
    """
    Null data class for SAX parser.

    Registering a tag with this class will render the text contents into
    None when finalize is called. All attributes and tags will be lost.
    All text will be lost.
    """

    __slots__ = ()

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('name', 'none')
        BaseNode.__init__(self, *args, **kwargs)

    def finalize(self):
        "Discard the character data"

    # pylint: disable-msg=C0111
    # docstring inherited from parent class
    def _iterChildren(self):
        return []

class BooleanNode(BaseNode):
    """
    Boolean data class for SAX parser.

    Registering a tag with this class will render the text contents into
    a bool when finalize is called. All attributes and tags will be lost.
    '1' or 'true' (case insensitive) will result in True.
    """

    __slots__ = ()

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('name', 'bool')
        BaseNode.__init__(self, *args, **kwargs)

    def finalize(self):
        "Convert the character data to a boolean value"
        text = self.getText()
        return self.fromString(text)

    @staticmethod
    def fromString(stringVal):
        """
        Convert character data to a boolean value
        @param stringVal: String value to be converted to boolean
        @type stringVal: C{str}
        @rtype: C{bool}
        """
        if isinstance(stringVal, bool):
            return stringVal
        return stringVal.strip().upper() in ('TRUE', '1')

    @staticmethod
    def toString(boolVal):
        """
        Convert boolean value to character data.
        @param boolVal: Boolean value to be converted
        @type boolVal: C{bool}
        @rtype: C{str}
        """
        return boolVal and "true" or "false"

    # pylint: disable-msg=C0111
    # docstring inherited from parent class
    def _iterChildren(self):
        yield self.toString(self.finalize())

#}


#{ Specialized objects that can be serialized
class SerializableList(list):
    """A List class that can be serialized to XML"""

    tag = None

    def getElementTree(self, parent = None):
        """Return a hierarchy of objects that represent the
        structure of the XML document.

        @param parent: An optional parent object.
        @type parent: C{SerializableObject} instance
        """
        elem = createElementTree(self._getName(), {}, {}, parent = parent)
        for child in self:
            child.getElementTree(parent = elem)
        return elem

    # pylint: disable-msg=C0111
    # docstring inherited from parent class
    def _getName(self):
        return self.tag

# pylint: disable-msg=R0903
# Too few public methods (1/2): this is an interface
class SlotBasedSerializableObject(SerializableObject):
    """
    A serializable object that uses the slots for defining the data that
    has to be serialized to XML
    """
    __slots__ = []
    tag = None

    def __eq__(self, obj):
        # We should only compare class instances
        if type(self) != type(obj):
            return False
        for key in self.__slots__:
            val = self.__getattribute__(key)
            val2 = obj.__getattribute__(key)
            if val != val2:
                return False
        return True

    def __ne__(self, obj):
        return not self.__eq__(obj)

    # pylint: disable-msg=C0111
    # docstring inherited from parent class
    def _getName(self):
        return self.tag

    # pylint: disable-msg=C0111
    # docstring inherited from parent class
    def _getLocalNamespaces(self):
        return {}

    # pylint: disable-msg=C0111
    # docstring inherited from parent class
    def _iterAttributes(self):
        return self._splitData()[0].items()

    # pylint: disable-msg=C0111
    # docstring inherited from parent class
    def _iterChildren(self):
        return self._splitData()[1]

    def _splitData(self):
        """
        Split attributes and child nodes from the slots
        @return: A tuple (attributes, children)
        @rtype: C{tuple}
        """
        attrs = {}
        children = []
        for fName in self.__slots__:
            fVal = getattr(self, fName)
            if isinstance(fVal, (bool, int, str, unicode)):
                attrs[fName] = fVal
            elif fVal is None:
                # Skip None values
                continue
            elif isinstance(fVal, list):
                children.append(fVal)
            else:
                if not hasattr(fVal, "getElementTree"):
                    raise XmlLibError(
                        "Expected an object implementing getElementTree")
                children.append(fVal)
        return attrs, children
#}

class ToplevelNode(object):
    """
    A class that extracts the first node out of an XML stream

    @ivar name: the name of the top-level node
    @type name: C{unicode}
    @ivar attrs: the node's attributes
    @type attrs: C{dict}
    """

    class _FirstTagFound(Exception):
        pass

    class _Handler(sax.ContentHandler):
        def __init__(self):
            sax.ContentHandler.__init__(self)
            self._name = None
            self._attrs = None

        def startElement(self, name, attrs):
            self._name = name
            self._attrs = dict((k, v) for (k, v) in attrs.items())
            raise ToplevelNode._FirstTagFound()

        def endElement(self, name):
            "This method should never be called"

        def characters(self, ch):
            "This method should never be called"

    def __init__(self, stream):
        """
        Read the top-level node.

        @param stream: the XML stream
        @type stream: C{str} or C{file}
        """
        self.name = None
        self.attrs = {}

        self.parseStream(stream)

    def parseStream(self, stream):
        """
        Parse the stream and extract the top-level node name and attributes.

        @param stream: the XML stream
        @type stream: C{str} or C{file}
        """
        if not hasattr(stream, 'read'):
            stream = StringIO.StringIO(stream)

        contentHandler = self._Handler()
        parser = sax.make_parser()
        parser.setContentHandler(contentHandler)
        try:
            parser.parse(stream)
        except sax.SAXParseException:
            return
        except self._FirstTagFound:
            self.name = contentHandler._name
            self.attrs = contentHandler._attrs
            return

    def getAttributesByNamespace(self, namespace):
        """
        Retrieve the top-level node's attributes associated with the specified
        namespace.

        Example::

            Given the XML specification:
            <node xmlns:x="urlX" x:a="1" x:b="2" attr="3" />

            the method, called with namespace "urlX", will return
            {"a" : "1", "b" : "2"}

        @return: The attributes associated with the namespace
        @rtype: dict
        """
        nsMap = {}
        otherAttrs = {}
        for k, v in self.attrs.items():
            arr = k.split(':', 1)
            if arr[0] == 'xmlns':
                if len(arr) == 1:
                    nsAlias = None
                else:
                    nsAlias = arr[1]
                nsMap[v] = nsAlias
            else:
                if len(arr) == 1:
                    attrNs, attrK = None, arr[0]
                else:
                    attrNs, attrK = arr
                otherAttrs.setdefault(attrNs, {})[attrK] = v
        if namespace not in nsMap:
            return {}
        return otherAttrs.get(nsMap[namespace], {})

#{ Binding classes
class BindingHandler(sax.ContentHandler):
    """
    Sax Content handler class.

    This class doesn't need to be instantiated directly. It will be invoked
    on an as-needed basis by DataBinder. This class interfaces with the
    Python builtin SAX parser and creates dynamic python objects based on
    registered node classes. If no nodes are registered, a python object
    structure that looks somewhat like a DOM tree will result.
    """
    def __init__(self, typeDict = None):
        if not typeDict:
            typeDict = {}
        self.typeDict = typeDict
        self.stack = []
        self.rootNode = None
        sax.ContentHandler.__init__(self)

    def registerType(self, typeClass, name = None, namespace = None):
        """
        Register a class as a node handler.
        @param typeClass: A node class to register
        @type typeClass: C{class}
        @param name: the node name for which C{dispatch} will instantiate the
        node type class. If None, the name and namespace will be extracted by
        calling the class-level method C{getTag} of the node type class.
        @type name: C{str} or None
        @param namespace: An optional namespace
        @type namespace: C{str} or None
        """
        if name is None:
            name = typeClass.name
        if namespace is None:
            namespace = getattr(typeClass, 'namespace', None)

        self.typeDict[(namespace, name)] = typeClass

    def startElement(self, name, attrs):
        "SAX parser callback invoked when a start element event is emitted"
        classType = GenericNode
        nameSpace, tagName = splitNamespace(name)
        if (nameSpace, tagName) in self.typeDict:
            classType = self.typeDict[(nameSpace, tagName)]

        if self.stack:
            nsMap = self.stack[-1].getNamespaceMap()
        else:
            nsMap = {}
        newNode = classType(attrs, nsMap = nsMap)
        newNode.setName(name)
        self.stack.append(newNode)

    def endElement(self, name):
        "SAX parser callback invoked when an end element event is emitted"
        elem = self._handleEndElement(name)
        self._processEndElement(elem)

    def _handleEndElement(self, name):
        elem = self.stack.pop()
        assert elem.getName() == name
        return elem

    def _processEndElement(self, elem):
        if not self.stack:
            self.rootNode = elem.finalize()
        else:
            self.stack[-1].addChild(elem)

    def characters(self, ch):
        "SAX parser callback invoked when character data is found"
        elem = self.stack[-1]
        elem.characters(ch)

class StreamingBindingHandler(BindingHandler):
    def __init__(self, typeDict=None):
        BindingHandler.__init__(self, typeDict=typeDict)
        self.generatedNodes = collections.deque()

    def endElement(self, name):
        "SAX parser callback invoked when an end element event is emitted"
        elem = self._handleEndElement(name)
        if getattr(elem, "WillYield", None):
            self.generatedNodes.append(elem.finalize())
            return
        self._processEndElement(elem)

    def next(self):
        if not self.generatedNodes:
            return None
        return self.generatedNodes.popleft()

    def clear(self):
        return self.generatedNodes.clear()

class DataBinder(object):
    """
    DataBinder class.

    This class wraps all XML parsing logic in this module.

    For the simple case, the binder can be used as-is, by invoking the
    C{parseString} method, in which case a hierarchy of C{BaseNode} objects
    will be produced. The top-level node can be also used for serializing
    back to XML

    EXAMPLE::

        binder = DataBinder()
        obj = binder.parseString('<baz><foo>3</foo><bar>test</bar></baz>')
        data = binder.toXml(prettyPrint = False)
        # data == '<baz><foo>3</foo><bar>test</bar></baz>'

    A node's attributes can be retrieved with C{iterAttributes}, and its
    children with C{iterChildren}. The node's text can be retrieved with
    C{getText}. Please note that we do not support character data and nodes
    mixed under the same parent. For insntance, the following XML construct
    will not be properly handled::

        <node>Some text<child>Child1</child>and some other text</node>

    To convert simple data types (like integer or boolean nodes) into their
    corresponding Python representation, you can use the built-in
    C{IntegerNode}, C{BooleanNode} and C{StringNode}. These objects implement
    a C{finalize} method that will convert the object's text into the proper
    data type (and ignore other possible child nodes).

    For a more convenient mapping of the data structures parsed from XML into
    rich Python objects, you can register your own classes, generally
    inherited from C{BaseNode}, that will overwrite the C{addChild} method to
    change the default behavior. You can choose to store children in a
    different way, instead of the default data structure of children.

    EXAMPLE::

        binder = xmllib.DataBinder()
        class MyClass(BaseNode):
            def addChild(self, child):
                if child.getName() == 'isPresent':
                    self.present = child.finalize()

        binder.registerType(MyClass, name = 'node')
        binder.registerType(BooleanNode, name = 'isPresent')

        obj = binder.parseString('<node><isPresent>true</isPresent></node>')
        # obj.isPresent == true

    parseFile: takes a a path and returns a python object.
    parseString: takes a string containing XML data and returns a python
    object.
    registerType: register a tag with a class defining how to treat XML content.
    toXml: takes an object and renders it into an XML representation.

    @cvar xmlSchemaNamespace: Namespace for XML schema. This should not
    change.
    @type xmlSchemaNamespace: C{str}

    """
    xmlSchemaNamespace = 'http://www.w3.org/2001/XMLSchema-instance'
    xmlBaseNamespace = 'http://www.w3.org/XML/1998/namespace'
    BindingHandlerFactory = BindingHandler

    def __init__(self, typeDict = None):
        """
        Initialize the Binder object.

        @param typeDict: optional type mapping object
        @type typeDict: dict
        """
        self.contentHandler = self.BindingHandlerFactory(typeDict)

    def registerType(self, klass, name = None, namespace = None):
        """
        Register a new class with a node name. As the XML parser encounters
        nodes, it will try to instantiate the classes registered with the
        node's name, and will fall back to the BaseNode class if a more
        specific class could not be found.

        If the optional keyword argument C{name} is not specified, the name
        of the node will be compared with the class' C{name} field (a
        class-level attribute).
        """
        return self.contentHandler.registerType(klass, name = name,
                                                namespace = namespace)

    def parseString(self, data, validate = False, schemaDir = None):
        """
        Parse an XML string.
        @param data: the XML string to be parsed
        @type data: C{str}
        @param validate: Validate before parsing (off by default)
        @type validate: C{bool}
        @param schemaDir: A directory where schema files are stored
        @type schemaDir: C{str}

        @return: a Node object
        @rtype: A previosly registered class (using C{registerType} or a
        C{BaseNode}.
        @raises C{UnknownSchemaError}: if no valid schema was found
        @raises C{InvalidXML}: if the XML is malformed.
        """
        stream = StringIO.StringIO(data)
        return self.parseFile(stream, validate = validate,
                              schemaDir = schemaDir)

    def parseFile(self, stream, validate = False, schemaDir = None):
        """
        Parse an XML file.
        @param stream: the XML file to be parsed
        @type stream: C{file}
        @param validate: Validate before parsing (off by default)
        @type validate: C{bool}
        @param schemaDir: A directory where schema files are stored
        @type schemaDir: C{str}

        @return: a Node object
        @rtype: A previosly registered class (using C{registerType} or a
        C{BaseNode}.
        @raises C{UnknownSchemaError}: if no valid schema was found
        @raises C{InvalidXML}: if the XML is malformed.
        """
        if isinstance(stream, str):
            stream = file(stream)
        origPos = stream.tell()
        try:
            if validate:
                stream.seek(0)
                self.validate(stream, schemaDir = schemaDir)
            stream.seek(0)

            return self._parse(stream)
        finally:
            stream.seek(origPos)

    @classmethod
    def getSchemaLocationsFromStream(cls, stream):
        """
        Extract the schema locations from an XML stream.
        @param stream: an XML stream
        @type stream: C{file}
        @return: A list of schema locations found in the document
        @rtype: C{list}
        @raises C{UnknownSchemaError}: if no schema location was specified in
        the trove.
        @raises C{InvalidXML}: if the XML is malformed.
        """
        # We need the schema location, so extract the top-level node

        # Make sure we roll the stream back where it was
        pos = stream.tell()
        tn = ToplevelNode(stream)
        stream.seek(pos)

        if tn.name is None:
            raise InvalidXML("Possibly malformed XML")
        attrs = tn.getAttributesByNamespace(cls.xmlSchemaNamespace)
        schemaLocation = attrs.get('schemaLocation')
        if schemaLocation is None:
            raise UnknownSchemaError(
                "Schema location not specified in XML stream")
        schemaFiles = [ os.path.basename(x) for x in schemaLocation.split() ]
        return schemaFiles

    @classmethod
    def chooseSchemaFile(cls, schemaFiles, schemaDir):
        """
        Given a list of schema files, choose the one that we can find in
        the specified directory.
        @param schemaFiles: A list of schema files
        @type schemaFiles: C{list}
        @param schemaDir: A directory where schema files reside
        @type schemaDir: C{str}
        @return: path to the schema file
        @rtype: C{str}
        @raises C{UnknownSchemaError}: if no valid schema was found
        """
        if schemaDir is None:
            raise UnknownSchemaError("Schema directory not specified")
        if not os.path.isdir(schemaDir):
            raise UnknownSchemaError("Schema directory `%s' not found" %
                schemaDir)

        # Pick up the first schema that we could find, in the order they were
        # specified
        localFiles = os.listdir(schemaDir)

        possibleSchema = set(schemaFiles).intersection(localFiles)
        if not possibleSchema:
            raise UnknownSchemaError(
                "No applicable schema found in directory `%s'" % schemaDir)

        for sch in schemaFiles:
            if sch in possibleSchema:
                return os.path.join(schemaDir, sch)

    @classmethod
    def validate(cls, stream, schemaDir = None):
        """
        Validate a stream against schema files found in a directory.
        @param stream: an XML stream
        @type stream: C{file}
        @param schemaDir: A directory where schema files reside
        @type schemaDir: C{str}
        @raises C{UnknownSchemaError}: if no valid schema was found
        @raises C{InvalidXML}: if the XML is malformed.
        """
        validSchema = cls.getSchemaLocationsFromStream(stream)
        schemaFile = cls.chooseSchemaFile(validSchema, schemaDir)

        schema = etree.XMLSchema(file = schemaFile)
        tree = etree.parse(stream)
        if not schema.validate(tree):
            raise SchemaValidationError(str(schema.error_log))

    @classmethod
    def toXml(cls, obj, prettyPrint = True):
        """
        Serialize an object to XML.

        @param obj: An object implementing a C{getElementTree} mthod.
        @type obj: C{obj}
        @param prettyPrint: if True (the default), the XML that is produced
        will be formatted for easier reading by humans (by introducing new
        lines and white spaces).
        @type prettyPrint: C{bool}
        @return: the XML representation of the object
        @rtype: str
        """
        tree = obj.getElementTree()
        res = etree.tostring(tree, pretty_print = prettyPrint,
            xml_declaration = True, encoding = 'UTF-8')
        return res

    def _parse(self, stream):
        self.contentHandler.rootNode = None
        parser = sax.make_parser()
        parser.setContentHandler(self.contentHandler)
        try:
            parser.parse(stream)
        except sax.SAXParseException:
            exc_info = sys.exc_info()
            raise InvalidXML, exc_info[1], exc_info[2]
        rootNode = self.contentHandler.rootNode
        self.contentHandler.rootNode = None
        return rootNode

class StreamingDataBinder(DataBinder):
    BindingHandlerFactory = StreamingBindingHandler

    class _Iterator(object):
        BUFFER_SIZE = 16 * 1024
        def __init__(self, parser, stream):
            self.parser = parser
            self.stream = stream
            self.contentHandler = self.parser.getContentHandler()
            self.contentHandler.clear()

        def __iter__(self):
            return self

        def next(self):
            node = self.contentHandler.next()
            if node is not None:
                return node
            buf = self.stream.read(self.BUFFER_SIZE)
            if not buf:
                self.parser.close()
                raise StopIteration()
            self.parser.feed(buf)
            return self.next()

    def _parse(self, stream):
        parser = sax.make_parser()
        parser.setContentHandler(self.contentHandler)
        return self._Iterator(parser, stream)
#}

def splitNamespace(tag):
    """
    Splits the namespace out of the tag.
    @param tag: tag
    @type tag: C{str}
    @return: A tuple with the namespace (set to None if not present) and
    the tag name.
    @rtype: C{tuple} (namespace, tagName)
    """
    arr = tag.split(':', 1)
    if len(arr) == 1:
        return None, tag
    return arr[0], arr[1]

def unsplitNamespace(name, namespace = None):
    """
    @param name: Name
    @type name: C{str}
    @param namespace: Namespace
    @type namespace: C{str} or None
    @return: the name qualified with the namespace
    @rtype: C{str}
    """
    if namespace is None:
        return name
    return "%s:%s" % (namespace, name)

def orderItems(items, order):
    """
    Reorder a list of items based on the order passed in as a list
    @param items:
    @type items: iterable
    @param order: list defining the items' ordering
    @type order: C{list}
    @return: the ordered list, unknown elements at the end
    @rtype: C{list}
    """
    # sort key is a three part tuple. each element maps to these rules:
    # element one reflects if we know how to order the element.
    # element two reflects the element's position in the ordering.
    # element three sorts everything else by simply providing the original
    # item (aka. default ordering of sort)
    orderHash = dict((y, i) for i, y in enumerate(order))
    return sorted(items,
        key = lambda x: (x.getName() not in orderHash,
                         orderHash.get(x.getName()),
                         x.getName()))

def createElementTree(name, attrs, nsMap = None, parent = None):
    """
    Create an element tree.

    @param name: Node name
    @type name: C{str}
    @param attrs: Node attributes
    @type attrs: C{dict}
    @param nsMap: A namespace alias to namespace mapping
    @type nsMap: C{dict}
    @param parent: An optional parent object.
    @type parent: C{etree.Element} instance
    @return: an element tree
    @rtype: C{etree.Element} instance
    """
    if nsMap is None:
        nsMap = {}
    if parent is not None:
        elem = etree.SubElement(parent, name, attrs, nsMap)
    else:
        elem = etree.Element(name, attrs, nsMap)
    return elem

class NodeDispatcher(object):
    """Simple class that dispatches nodes of various types to various
    registered classes.

    The registered classes need to implement a C{getTag()} static method or
    class method, that returns the name of the tags we want to be registered
    with this node.
    """

    def __init__(self, nsMap = None):
        """
        @param nsMap: a namespace mapping from aliases to the namespace
        string. For example, for the following declaration::

            <node xmlns="namespace1" xmlns:ns="namespace2"/>

        the mapping will be {None: "namespace1", "ns" : "namespace2"}
        @type nsMap: C{dict}
        """

        self._dispatcher = {}
        self._nsMap = nsMap or {}

    def registerType(self, typeClass, name = None, namespace = None):
        """
        Register a class as a node handler.
        @param typeClass: A node class to register
        @type typeClass: C{class}
        @param name: the node name for which C{dispatch} will instantiate the
        node type class. If None, the name and namespace will be extracted by
        calling the class-level method C{getTag} of the node type class.
        @type name: C{str} or None
        @param namespace: An optional namespace
        @type namespace: C{str} or None
        """
        if name is None:
            if not hasattr(typeClass, 'getTag'):
                return
            ns, name = splitNamespace(typeClass.getTag())
        else:
            ns, name = namespace, name

        key = "{%s}%s" % (self._nsMap.get(ns, ''), name)
        self._dispatcher[key] = typeClass

    def registerClasses(self, module, baseClass):
        """
        Register all classes that are a subclass of baseClass and are part
        of the module.
        @param module: The module in which supported classes will be looked up.
        @type module: module
        @param baseClass: A base class for all the classes that have to be
        registered.
        @type baseClass: class
        """
        for symVal in module.__dict__.itervalues():
            if not isinstance(symVal, type):
                continue
            if issubclass(symVal, baseClass) and symVal != baseClass:
                self.registerType(symVal)

    def dispatch(self, node):
        """
        Create objects for this node, based on the classes registered with
        the dispatcher.
        """

        absName = node.getAbsoluteName()
        if absName not in self._dispatcher:
            return None
        nodeClass = self._dispatcher.get(absName)

        return nodeClass(node)
