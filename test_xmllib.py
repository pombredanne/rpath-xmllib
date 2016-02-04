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


import os
import shutil
import StringIO
import tempfile
import unittest


from lxml import etree

import api as xmllib
import collections



class TestCase(unittest.TestCase):
    """
    Originally from https://raw.githubusercontent.com/sassoftware/testutils/6a59ca20f02a5841ebebc9806e9d2e5e1c3d9e0a/testrunner/testcase.py
    Stripped down to the bare minimum needed here.
    """

    def assertRaises(self, excClass, callableObj=None, *args, **kwargs):
        # Override so that the exception is returned. But also try to pass
        # through the context manager feature added in Python 2.7
        if callableObj is None:
            return unittest.TestCase.assertRaises(self, excClass, callableObj,
                    *args, **kwargs)
        try:
            callableObj(*args, **kwargs)
        except excClass, err:
            return err
        else:
            try:
                exc_name = excClass.__name__
            except AttributeError:
                exc_name = str(excClass)
            raise self.failureException("%s not raised" % exc_name)
    failUnlessRaises = assertRaises

    @classmethod
    def _strip(cls, data):
        if data is None:
            return None
        # Convert empty string to None
        return data.strip() or None

    @classmethod
    def _nodecmp(cls, node1, node2):
        if node1.attrib != node2.attrib:
            return False
        if node1.nsmap != node2.nsmap:
            return False
        children1 = node1.getchildren()
        children2 = node2.getchildren()

        if children1 or children2:
            # Compare text in nodes that have children (mixed content).
            # We shouldn't have mixed content, but we need to be flexible.
            if cls._strip(node1.text) != cls._strip(node2.text):
                return False
            if len(children1) != len(children2):
                return False
            for ch1, ch2 in zip(children1, children2):
                if not cls._nodecmp(ch1, ch2):
                    return False
            return True
        # No children, compare the text
        return node1.text == node2.text

    @classmethod
    def _removeTail(self, node):
        stack = collections.deque([ node ])
        while stack:
            n = stack.pop()
            n.tail = None
            children = n.getchildren()
            if children:
                # We don't accept mixed content
                n.text = None
            stack.extend(n.getchildren())
        return node

    def assertXMLEquals(self, first, second):
        tree0 = self._removeTail(etree.fromstring(first.strip()))
        tree1 = self._removeTail(etree.fromstring(second.strip()))
        if not self._nodecmp(tree0, tree1):
            data0 = etree.tostring(tree0, pretty_print=True, with_tail=False)
            data1 = etree.tostring(tree1, pretty_print=True, with_tail=False)
            import difflib
            diff = '\n'.join(list(difflib.unified_diff(data0.splitlines(),
                    data1.splitlines()))[2:])
            self.fail(diff)



class BaseTest(TestCase):
    pass

class DataBindingNodeTest(BaseTest):
    def testSerializableNodeInterface(self):
        node = xmllib.SerializableObject()
        self.failUnlessRaises(NotImplementedError, node._getName)
        self.failUnlessRaises(NotImplementedError, node._getLocalNamespaces)
        self.failUnlessRaises(NotImplementedError, node._iterAttributes)
        self.failUnlessRaises(NotImplementedError, node._iterChildren)
        self.failUnlessRaises(NotImplementedError, node.getElementTree)

    def testIterAttributes(self):
        refAttrs = {'xmlns' : 'a', 'xmlns:ns' : 'b',
                    'ns:attr1' : 'val1', 'attr2' : 'val2'}
        node = xmllib.BaseNode(refAttrs)
        attrs = dict(x for x in node.iterAttributes())
        self.failUnlessEqual(attrs, refAttrs)

        node.setName('ns:foo')
        binder = xmllib.DataBinder()
        self.assertXMLEquals(binder.toXml(node, prettyPrint = False),
            '<ns:foo xmlns="a" xmlns:ns="b" attr2="val2" ns:attr1="val1"/>')

    def testGetChildren(self):
        binder = xmllib.DataBinder()
        rootNode = binder.parseFile(StringIO.StringIO("""
<nsB:root xmlns="def" xmlns:nsA="a" xmlns:nsB="b">
  <nsA:child>childA</nsA:child>
  <nsB:child>childB</nsB:child>
  <child>childDef</child>
</nsB:root>
"""))
        self.failUnlessEqual([ x.getText()
            for x in rootNode.getChildren('child', 'nsA')], ['childA'])
        self.failUnlessEqual([ x.getText()
            for x in rootNode.getChildren('child', 'nsB')], ['childB'])
        self.failUnlessEqual([ x.getText()
            for x in rootNode.getChildren('child')], ['childDef'])


    def testGetAttribute(self):
        # We are redefining namespace nsC, which is not supported
        refAttrs = {'xmlns' : 'a', 'xmlns:nsB' : 'b', 'xmlns:nsC' : 'b',
                    'attr' : 'val1', 'nsB:attr' : 'val2', 'nsC:attr' : 'val3'}
        node = xmllib.BaseNode(refAttrs, name = 'root')
        self.failUnlessEqual(node.getAttribute('attr'), 'val1')
        self.failUnlessEqual(node.getAttribute('attr', 'nsB'), 'val2')
        self.failUnlessEqual(node.getAttribute('attr', 'nsC'), 'val3')
        self.failUnlessEqual(node.getAttribute('attr', 'EEE'), None)

        self.failUnlessEqual(node.getAttributeByNamespace('attr'), 'val1')
        self.failUnlessEqual(node.getAttributeByNamespace('attr', 'a'), 'val1')
        # This is the same attribute, we just happen to have two identical
        self.failUnlessEqual(node.getAttributeByNamespace('attr', 'b'), 'val2')
        self.failUnlessEqual(node.getAttributeByNamespace('attr', 'E'), None)

        # Make sure we get the right namespaces albeit dubplicated)
        self.failUnlessEqual(list(node.iterNamespaces()),
            [(None, 'a'), ('nsB', 'b'), ('nsC', 'b')])


        # lxml will notice the re-definition of a namespace
        binder = xmllib.DataBinder()
        self.assertXMLEquals(binder.toXml(node, prettyPrint = False),
            '<root xmlns="a" xmlns:nsB="b" xmlns:nsC="b" nsB:attr="val3" attr="val1"/>')

    def testSlotBased(self):
        class S(xmllib.SlotBasedSerializableObject):
            tag = 'Blah'
            __slots__ = ['attr1', 'child1', 'maybe']

        binder = xmllib.DataBinder()

        node = S()
        node.attr1 = 1
        node.child1 = xmllib.BooleanNode().characters('true')
        node.maybe = xmllib.StringNode().characters('Maybe')

        self.assertXMLEquals(binder.toXml(node, prettyPrint = False),
            '<Blah attr1="1"><bool>true</bool><string>Maybe</string></Blah>')

        node.maybe = {}
        self.failUnlessRaises(xmllib.XmlLibError, binder.toXml, node)

    def testSlotBasedEq(self):
        class WithSlots(xmllib.SlotBasedSerializableObject):
            tag = "something"
            __slots__ = ['foo']

        node1 = WithSlots()
        node2 = WithSlots()

        node1.foo = 'foo'
        node2.foo = 'foo'

        self.assertEquals(node1, node2)

        node1.foo = 'foo'
        node2.foo = 'fo0'

        self.assertEquals(node1 == node2, False)
        self.assertEquals(node1 != node2, True)

    def testUndefinedNamespace(self):
        attrs = {'ns:attr1' : 'val1'}
        self.failUnlessRaises(xmllib.UndefinedNamespaceError,
                              xmllib.BaseNode, attrs)

    def testCreateElementTree(self):
        attrs = {'{a}attr1' : 'val1', 'xmlns' : 'b'}
        ns = {'ns' : 'a'}
        n = xmllib.createElementTree('node', attrs, ns)
        self.assertXMLEquals(etree.tostring(n),
            '<node xmlns:ns="a" ns:attr1="val1" xmlns="b"/>')

        attrs = {'{a}attr1' : 'va11', '{c}attr2' : 'val2'}
        ns = {'nsc' : 'c'}
        n2 = xmllib.createElementTree('{c}subnode', attrs, ns, parent = n)
        self.assertXMLEquals(etree.tostring(n),
            '<node xmlns:ns="a" ns:attr1="val1" xmlns="b">'
              '<nsc:subnode xmlns:nsc="c" ns:attr1="va11" nsc:attr2="val2"/>'
            '</node>')

        n3 = xmllib.createElementTree('{a}subnode', {}, parent = n)
        n3.text = 'node text'
        self.assertXMLEquals(etree.tostring(n),
            '<node xmlns:ns="a" ns:attr1="val1" xmlns="b">'
              '<nsc:subnode xmlns:nsc="c" ns:attr1="va11" nsc:attr2="val2"/>'
              '<ns:subnode>node text</ns:subnode>'
            '</node>')

    def testSplitNamespace(self):
        self.failUnlessEqual(xmllib.splitNamespace('a'), (None, 'a'))
        self.failUnlessEqual(xmllib.splitNamespace('b:a'), ('b', 'a'))

    def testUnsplitNamespace(self):
        self.failUnlessEqual(xmllib.unsplitNamespace('a'), 'a')
        self.failUnlessEqual(xmllib.unsplitNamespace('a', None), 'a')
        self.failUnlessEqual(xmllib.unsplitNamespace('a', 'b'), 'b:a')

    def testGetAbsoluteName(self):
        # No namespace specified
        node = xmllib.BaseNode()
        node.setName('foo')
        self.failUnlessEqual(node.getAbsoluteName(), 'foo')

        # With a default namespace
        node = xmllib.BaseNode(dict(xmlns = "a"))
        node.setName('foo')
        self.failUnlessEqual(node.getAbsoluteName(), '{a}foo')

        # With a namespace
        node = xmllib.BaseNode({'xmlns' : 'b', 'xmlns:ns' : 'a'})
        node.setName('ns:foo')
        self.failUnlessEqual(node.getAbsoluteName(), '{a}foo')
        node.setName('foo')
        self.failUnlessEqual(node.getAbsoluteName(), '{b}foo')

        # With a bad namespace
        self.failUnlessRaises(xmllib.UndefinedNamespaceError,
                              node.setName, 'nosuchns:foo')

    def testIntObj(self):
        node = xmllib.IntegerNode()
        node.characters('3')
        self.assertEquals(node.finalize(), 3)

    def testIntObjInfoLoss(self):
        node = xmllib.IntegerNode()

        self.failUnlessRaises(AttributeError, setattr, node, 'garbage', 'data')

        node.__class__.test = 'foo'
        res = node.finalize()
        self.failIf(hasattr(res.__class__, 'test'))
        self.assertEquals(res, 0)

    def testStringObj(self):
        node = xmllib.StringNode()
        node.characters('foo')
        self.assertEquals(node.finalize(), 'foo')

    def testBooleanNode(self):
        node = xmllib.BooleanNode()
        node.characters('true')
        self.assertEquals(node.finalize(), True)

        node = xmllib.BooleanNode()
        node.characters('False')
        self.assertEquals(node.finalize(), False)

        node = xmllib.BooleanNode()
        node.characters('1')
        self.assertEquals(node.finalize(), True)

        node = xmllib.BooleanNode()
        node.characters('0')
        self.assertEquals(node.finalize(), False)

        self.failUnlessEqual(node.fromString(True), True)
        self.failUnlessEqual(node.fromString(False), False)
        self.failUnlessEqual(node.fromString("tRuE"), True)
        self.failUnlessEqual(node.fromString("1"), True)
        self.failUnlessEqual(node.fromString("abcde"), False)

    def testNullNode(self):
        node = xmllib.NullNode()
        node.characters('anything at all')
        self.assertEquals(node.finalize(), None)

        binder = xmllib.DataBinder()
        self.assertXMLEquals(binder.toXml(node, prettyPrint = False),
                             "<none/>")

    def testCompositeNode(self):
        class CompNode(xmllib.BaseNode):
            _singleChildren = ['integerData', 'stringData']

        node = CompNode()
        child = xmllib.IntegerNode(name = 'integerData')
        child.characters('3')
        node.addChild(child)
        self.assertEquals(node.integerData, 3)

        child = xmllib.StringNode(name = 'stringData')
        child.setName('stringData')
        child.characters('foo')
        node.addChild(child)
        self.assertEquals(node.stringData, 'foo')

        child = xmllib.StringNode(name = 'unknownData')
        child.characters('bar')
        node.addChild(child)
        self.failIf(hasattr(node, 'unknownData'))
        self.failUnlessEqual([ x for x in node.iterChildren() ], ['bar'])

class ContentHandlerTest(BaseTest):
    def testInvalidData(self):
        data = "vadfadfadf"
        binder = xmllib.DataBinder()
        self.failUnlessRaises(xmllib.InvalidXML,
            binder.parseString, data)

    def testToplevelNode(self):
        # Some invalid XML
        data = "vadfadfadf"
        tn = xmllib.ToplevelNode(data)
        self.failUnlessEqual(tn.name, None)

        # Invalid XML (but the sax parser should not notice the lack of a
        # close tag)
        data = '''<?xml version="1.0"?>
<node xmlns="a" xmlns:xsi="b" xsi:schemaLocation="c" xsi:q="q" attr="d">blah'''
        tn = xmllib.ToplevelNode(data)
        self.failUnlessEqual(tn.name, 'node')

        # Valid XML
        data2 = data + "<node>"
        tn = xmllib.ToplevelNode(data2)
        self.failUnlessEqual(tn.name, 'node')
        self.failUnlessEqual(tn.attrs, {'xmlns' : 'a', 'xmlns:xsi' : 'b',
            'xsi:schemaLocation' : 'c', 'attr' : 'd', 'xsi:q' : 'q'})

        self.failUnlessEqual(tn.getAttributesByNamespace('b'),
            {'schemaLocation' : 'c', 'q' : 'q'})
        self.failUnlessEqual(tn.getAttributesByNamespace('a'),
            {'attr' : 'd'})
        self.failUnlessEqual(tn.getAttributesByNamespace('nosuchns'),
            {})



    def testHandlerRegisterType(self):
        hdlr = xmllib.BindingHandler()
        self.assertEquals(hdlr.typeDict, {})
        hdlr.registerType(xmllib.StringNode, 'foo')
        self.assertEquals(hdlr.typeDict, {(None, 'foo'): xmllib.StringNode})

        hdlr = xmllib.BindingHandler()
        hdlr.registerType(xmllib.StringNode, 'foo', namespace = 'ns0')
        self.assertEquals(hdlr.typeDict, {('ns0', 'foo'): xmllib.StringNode})

        hdlr = xmllib.BindingHandler({(None, 'bar'): xmllib.IntegerNode})
        self.assertEquals(hdlr.typeDict, {(None, 'bar'): xmllib.IntegerNode})

    def testStartElement(self):
        hdlr = xmllib.BindingHandler({(None, 'foo'): xmllib.StringNode})

        hdlr.startElement('foo', {})
        self.assertEquals(len(hdlr.stack), 1)
        self.assertEquals(hdlr.stack[0].__class__.__name__ , 'StringNode')
        assert isinstance(hdlr.stack[0], xmllib.StringNode)

        hdlr.startElement('bar', {'attr1': '1'})
        self.assertEquals(len(hdlr.stack), 2)
        self.assertEquals(hdlr.stack[1].__class__.__name__ , 'GenericNode')
        assert isinstance(hdlr.stack[1], xmllib.GenericNode)
        self.assertEquals(hdlr.stack[1].getAttribute('attr1'), '1')

    def testEndElement1(self):
        hdlr = xmllib.BindingHandler()
        node1 = xmllib.BaseNode(name = 'foo')
        node2 = xmllib.BaseNode(name = 'foo')
        hdlr.stack = [node1, node2]
        hdlr.endElement('foo')
        self.assertEquals(hdlr.rootNode, None)
        self.assertEquals(len(hdlr.stack), 1)
        self.assertEquals(hdlr.stack[0], node1)
        self.failIf(hdlr.stack[0] == node2)

        hdlr.endElement('foo')
        self.assertEquals(hdlr.rootNode, node1)
        self.assertEquals(len(hdlr.stack), 0)

    def testEndElement2(self):
        class RecordNode(xmllib.BaseNode):
            def __init__(x, name = None):
                x.called = False
                xmllib.BaseNode.__init__(x, name = name)
            def addChild(x, child):
                assert isinstance(child, xmllib.BaseNode)
                x.called = True
                return xmllib.BaseNode.addChild(x, child)
        hdlr = xmllib.BindingHandler()
        node1 = RecordNode(name = 'foo')
        node2 = xmllib.BaseNode(name = 'foo')
        hdlr.stack = [node1, node2]
        hdlr.endElement('foo')
        self.assertEquals(node1.called, True)

    def testCharacters1(self):
        hdlr = xmllib.BindingHandler()
        node = xmllib.BaseNode()
        hdlr.stack = [node]
        hdlr.characters('foo')

        self.assertEquals(node.getText(), 'foo')

    def testCharacters2(self):
        class RecordNode(xmllib.BaseNode):
            def __init__(x):
                x.called = False
                xmllib.BaseNode.__init__(x)
            def characters(x, ch):
                x.called = True

        hdlr = xmllib.BindingHandler()
        node = RecordNode()
        hdlr.stack = [node]
        hdlr.characters('foo')

        self.assertEquals(node.called, True)

    def testStreaming(self):
        vals = range(5)
        class Root(xmllib.BaseNode):
            pass

        class Pkg(xmllib.BaseNode):
            WillYield = True
            _singleChildren = [ 'val' ]

        class Val(xmllib.IntegerNode):
            pass

        xml = "<root>%s</root>" % ''.join(
            "<pkg><val>%s</val></pkg>" % i for i in vals)

        hdlr = xmllib.StreamingDataBinder()
        hdlr.registerType(Root, name = "root")
        hdlr.registerType(Pkg, name = "pkg")
        hdlr.registerType(Val, name = "val")

        it = hdlr.parseString(xml)
        self.failUnlessEqual([ x.val for x in it ], vals)

        sio = StringIO.StringIO(xml)
        # Same deal with a tiny buffer size, to make sure we're incrementally
        # parsing
        it = hdlr.parseFile(sio)
        it.BUFFER_SIZE = 2
        self.failUnlessEqual(it.next().val, 0)
        self.failUnlessEqual(sio.tell(), 30)

        self.failUnlessEqual(it.next().val, 1)
        self.failUnlessEqual(it.parser.getColumnNumber(), 52)

        self.failUnlessEqual(it.next().val, 2)
        self.failUnlessEqual(it.parser.getColumnNumber(), 75)

        self.failUnlessEqual(it.next().val, 3)
        self.failUnlessEqual(it.parser.getColumnNumber(), 98)

class BinderTest(BaseTest):
    def testBinderRegisterType(self):
        binder = xmllib.DataBinder()
        binder.registerType(xmllib.StringNode, 'foo')
        self.assertEquals(binder.contentHandler.typeDict,
                {(None, 'foo'): xmllib.StringNode})

        binder = xmllib.DataBinder({(None, 'bar'): xmllib.IntegerNode})
        self.assertEquals(binder.contentHandler.typeDict,
                {(None, 'bar'): xmllib.IntegerNode})

    def testParseString(self):
        class ComplexType(xmllib.BaseNode):
            def addChild(slf, childNode):
                if childNode.getName() == 'foo':
                    slf.foo = childNode.finalize()
                elif childNode.getName() == 'bar':
                    slf.bar = childNode.finalize()

        binder = xmllib.DataBinder()
        binder.registerType(xmllib.IntegerNode, 'foo')
        binder.registerType(xmllib.StringNode, 'bar')
        binder.registerType(ComplexType, 'baz')

        data = '<baz><foo>3</foo><bar>test</bar></baz>'
        obj = binder.parseString(data)

        self.assertEquals(obj.foo, 3)
        self.assertEquals(obj.bar, 'test')
        self.assertEquals(obj.getName(), 'baz')

    def testRoundTripGenericParsing(self):
        binder = xmllib.DataBinder()
        data = '<baz><foo>3</foo><bar>test</bar></baz>'
        obj = binder.parseString(data)

        data2 = binder.toXml(obj, prettyPrint = False)
        self.assertXMLEquals(data, data2)

    def testParseFile(self):
        class ComplexType(xmllib.BaseNode):
            _singleChildren = ['foo', 'bar']

        binder = xmllib.DataBinder()
        binder.registerType(xmllib.BooleanNode, 'foo')
        binder.registerType(xmllib.NullNode, 'bar')
        binder.registerType(ComplexType, 'baz')

        data = '<baz><foo>TRUE</foo><bar>test</bar></baz>'
        fd, tmpFile = tempfile.mkstemp()
        try:
            os.close(fd)
            f = open(tmpFile, 'w')
            f.write(data)
            f.close()
            obj = binder.parseFile(tmpFile)
        finally:
            os.unlink(tmpFile)

        self.assertEquals(obj.foo, True)
        self.assertEquals(obj.bar, None)
        self.assertEquals(obj.getName(), 'baz')

    def testIterChildren(self):
        binder = xmllib.DataBinder()
        class Foo(xmllib.BaseNode):
            def iterChildren(self):
                if hasattr(self, 'bar'):
                    yield self.bar
                if hasattr(self, 'foo'):
                    yield xmllib.StringNode(name = 'foo').characters(
                        xmllib.BooleanNode.toString(self.foo))
                if hasattr(self, 'test'):
                    yield xmllib.StringNode(name = 'test').characters(self.test)
        foo = Foo(name = 'Foo')
        foo.foo = True
        foo.bar = Foo(name = 'bar')
        foo.bar.test = '123'
        data = binder.toXml(foo)
        self.assertXMLEquals(data, "<?xml version='1.0' encoding='UTF-8'?>"
                '\n<Foo>\n  <bar>\n'
                '    <test>123</test>\n  </bar>\n  <foo>true</foo>\n</Foo>')

        obj = binder.parseString(data)
        data2 = binder.toXml(obj)
        self.assertXMLEquals(data, data2)

    def testIterChildren2(self):
        binder = xmllib.DataBinder()
        binder.registerType(xmllib.BooleanNode, 'foo')

        class Foo(xmllib.BaseNode):
            def iterChildren(self):
                if hasattr(self, 'bar'):
                    yield self.bar
                if hasattr(self, 'foo'):
                    yield xmllib.StringNode(name = 'foo').characters(
                        xmllib.BooleanNode.toString(self.foo))
                if hasattr(self, 'test'):
                    yield xmllib.StringNode(name = 'test').characters(self.test)

        foo = Foo(name = 'Foo')
        foo.foo = True
        foo.bar = Foo(name = 'bar')
        foo.bar.test = '123'

        data = binder.toXml(foo)
        self.assertXMLEquals(data,
                '\n'.join((
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    '<Foo>',
                    '  <bar>',
                    '    <test>123</test>',
                    '  </bar>',
                    '  <foo>true</foo>',
                    '</Foo>')))

    def testToXmlInt(self):
        binder = xmllib.DataBinder()
        intObj = xmllib.IntegerNode(name = 'foo').characters('3')
        self.assertXMLEquals(binder.toXml(intObj, prettyPrint = False),
                                          '<foo>3</foo>')
        intObj = xmllib.IntegerNode().characters('3')
        self.assertXMLEquals(binder.toXml(intObj, prettyPrint = False),
                                          '<int>3</int>')

    def testToXmlBool(self):
        binder = xmllib.DataBinder()
        node = xmllib.BooleanNode(name = 'foo').characters('1')
        self.assertXMLEquals(binder.toXml(node, prettyPrint = False),
                             "<foo>true</foo>")
        node = xmllib.BooleanNode(name = 'foo').characters('tRue')
        self.assertXMLEquals(binder.toXml(node, prettyPrint = False),
                             "<foo>true</foo>")
        node = xmllib.BooleanNode(name = 'foo').characters('False')
        self.assertXMLEquals(binder.toXml(node, prettyPrint = False),
                             "<foo>false</foo>")

        node = xmllib.BooleanNode().characters('tRue')
        self.assertXMLEquals(binder.toXml(node, prettyPrint = False),
                             "<bool>true</bool>")

    def testToXmlList2(self):
        binder = xmllib.DataBinder()
        class ListObj(xmllib.SerializableList):
            tag = "toplevel"

        class Node1(xmllib.SlotBasedSerializableObject):
            __slots__ = [ 'attr1', 'attr2', 'attr3', 'children' ]
            tag = "node1"

        l1 = ListObj()
        n1 = Node1()
        l1.append(n1)

        n1.attr1 = "attrVal11"
        n1.attr2 = 12
        n1.attr3 = None
        n1.children = xmllib.StringNode(name = "child11").characters("text 11")

        n2 = Node1()
        l1.append(n2)

        n2.attr1 = 21
        n2.attr2 = "attrVal21"
        n2.attr3 = True
        # Add a list of elements as children of n2
        l2 = ListObj()
        l2.tag = "list2"
        l2.append(xmllib.StringNode(name = "child21").characters("text 21"))
        l2.append(xmllib.StringNode(name = "child31").characters("text 31"))

        n2.children = l2

        xmlData = binder.toXml(l1)
        self.assertXMLEquals(xmlData, """
<?xml version='1.0' encoding='UTF-8'?>
<toplevel>
  <node1 attr2="12" attr1="attrVal11">
    <child11>text 11</child11>
  </node1>
  <node1 attr2="attrVal21" attr3="true" attr1="21">
    <list2>
      <child21>text 21</child21>
      <child31>text 31</child31>
    </list2>
  </node1>
</toplevel>
""")

    def testToXmlUnicode(self):

        class Foo(xmllib.BaseNode):
            pass

        binder = xmllib.DataBinder()
        binder.registerType('foo', Foo)

        foo = Foo({u'birth-place' :  u'K\u00f6ln'}, name = 'Foo')
        marriage = xmllib.BaseNode(name = 'marriage')
        marriage.characters(u'Troms\xf8')
        foo.addChild(marriage)

        self.assertXMLEquals(binder.toXml(foo, prettyPrint = False),
            '<Foo birth-place="%s"><marriage>%s</marriage></Foo>' %
                ('K&#xF6;ln', 'Troms\xc3\xb8'))

        targetData = '<?xml version="1.0" encoding="UTF-8"?>\n' \
            '<Foo birth-place="K&#xF6;ln">\n  <marriage>Troms\xc3\xb8</marriage>\n</Foo>'

        self.assertXMLEquals(binder.toXml(foo), targetData)
        # Make sure we can still load the string
        obj = binder.parseString(binder.toXml(foo))

    def testUnkNodeVsStringNode(self):
        data = "<build><foo>123</foo></build>"
        binder = xmllib.DataBinder()
        obj = binder.parseString(data)
        assert isinstance(obj.getChildren('foo')[0], xmllib.BaseNode)
        self.assertEquals(obj.getChildren('foo')[0].getText(), '123')

        binder.registerType(xmllib.StringNode, 'foo')
        obj = binder.parseString(data)
        self.assertEquals([ x for x in obj.iterChildren() ],
                          ['123'])

    def testAttributesVsTags(self):
        class Foo(object):
            test = 42

            def getElementTree(slf, parent = None):
                elem = etree.Element('Foo', dict(test=str(slf.test)))
                if parent is not None:
                    parent.append(elem)
                return elem

        binder = xmllib.DataBinder()
        foo = Foo()
        data = binder.toXml(foo, prettyPrint = False)
        self.assertXMLEquals(data, '<Foo test="42"/>')

        foo.test = 14
        data2 = binder.toXml(foo, prettyPrint = False)
        self.assertXMLEquals(data2, '<Foo test="14"/>')

        class FooNode(xmllib.BaseNode):
            def addChild(slf, child):
                if child.getName() == 'test':
                    slf.test = child.finalize()

            def finalize(slf):
                t = slf.getAttribute('test')
                if t is not None:
                    slf.test = int(t)
                return slf

        binder = xmllib.DataBinder()
        binder.registerType(xmllib.IntegerNode, 'test')
        binder.registerType(FooNode, 'Foo')
        obj = binder.parseString(data2)

        # test that conflicting attributes and tags were preserved
        self.assertEquals(obj.test, 14)

    def testChildOrder(self):
        binder = xmllib.DataBinder()
        ordering = ['foo']
        items = [ xmllib.BaseNode(name = x) for x in ['foo', 'bar']]

        # prove that items in the ordering are listed first
        self.assertEquals(xmllib.orderItems(items, ordering), items)
        self.assertEquals(xmllib.orderItems(reversed(items), ordering), items)
        ordering = ['foo', 'bar']
        items = [ xmllib.BaseNode(name = x)
            for x in ['biff', 'baz', 'bar', 'foo'] ]
        ref = [items[3], items[2], items[1], items[0]]

        # prove ordering of listed items are by list. ordering of other
        # items is lexigraphical
        self.assertEquals(xmllib.orderItems(items, ordering), ref)

        # prove that it's ok to have items missing from ordering
        ordering = ['foo', 'bar', 'unused']
        items.append(xmllib.BaseNode(name = 'another'))
        ref.insert(2, items[-1])
        self.assertEquals(xmllib.orderItems(items, ordering), ref)


class RoundTripTest(BaseTest):
    def testXml2Obj2Xml(self):
        origData = "<?xml version='1.0' encoding='UTF-8'?>\n<build>\n  <foo>123</foo>\n  <foo>\xc3\xb6</foo>\n</build>"
        binder = xmllib.DataBinder()
        binder.registerType('foo', xmllib.StringNode)
        obj = binder.parseString(origData)
        data = binder.toXml(obj)
        self.assertXMLEquals(origData, data)

    def testXmlAttrs(self):
        origData = """<?xml version='1.0' encoding='UTF-8'?>\n<build data="1">\n  <foo>123</foo>\n</build>"""
        binder = xmllib.DataBinder()
        obj = binder.parseString(origData)
        data = binder.toXml(obj)
        self.assertXMLEquals(origData, data)

    def testXmlAttrs2(self):
        origData = """<?xml version='1.0' encoding='UTF-8'?>\n<build data="1">\n  <foo>123</foo>\n</build>"""
        refData = '<build data="1"><foo>123</foo></build>'
        binder = xmllib.DataBinder()
        obj = binder.parseString(origData)
        data = binder.toXml(obj)
        self.assertXMLEquals(origData, data)

    def testRoundTripDefault(self):
        binder = xmllib.DataBinder()
        data = '\n'.join(('<?xml version="1.0" encoding="UTF-8"?>',
            '<foo>',
            '  <baz>More text</baz>',
            '  <bar>This is some text</bar>',
            '</foo>'))

        data2 = '\n'.join(('<?xml version="1.0" encoding="UTF-8"?>',
            '<foo>',
            '  <bar>This is some text</bar>',
            '  <baz>More text</baz>',
            '</foo>'))

        obj = binder.parseString(data)
        newData = binder.toXml(obj)
        # this child node ordering is influenced by the order of the nodes
        # in the original xml blob
        self.assertXMLEquals(newData, data)

        class Foo(xmllib.BaseNode):
            name = 'foo'
            _childOrder = ['baz', 'bar']

        binder = xmllib.DataBinder()
        binder.registerType(Foo)
        obj = binder.parseString(data2)

        newData = binder.toXml(obj)
        self.assertXMLEquals(newData, data)

    def testNamespaceSupport(self):
        binder = xmllib.DataBinder()
        data = '\n'.join(('<?xml version="1.0" encoding="UTF-8"?>',
            '<gah:root-node xmlns="http://example.com"'
                ' xmlns:gah="http://exmaple.com/gah">',
            '  <gah:baz>More text</gah:baz>',
            '</gah:root-node>'))

        obj = binder.parseString(data)
        ndata = binder.toXml(obj)
        self.assertXMLEquals(data, ndata)

    def testXmlBaseNamespaceSupport(self):
        binder = xmllib.DataBinder()
        data = '\n'.join(('<?xml version="1.0" encoding="UTF-8"?>',
            '<gah:root-node xmlns="http://example.com"'
                ' xmlns:gah="http://exmaple.com/gah" xml:base="media://foo">',
            '  <gah:baz>More text</gah:baz>',
            '</gah:root-node>'))

        obj = binder.parseString(data)
        ndata = binder.toXml(obj)
        self.assertXMLEquals(data, ndata)
        self.failUnlessEqual(obj.getAttributeByNamespace('base', namespace='http://www.w3.org/XML/1998/namespace'),
            'media://foo')

    def testDispatcherRegisterClasses(self):
        class Coll1:
            class BaseType(object):
                @classmethod
                def getTag(kls):
                    return kls.tag

                def __init__(self, node):
                    self.node = node

            class ClassA(BaseType):
                tag = 'A'

            class ClassB(BaseType):
                tag = 'B'

        disp = xmllib.NodeDispatcher()
        disp.registerClasses(Coll1,Coll1.BaseType)
        self.failUnlessEqual(disp._dispatcher,
            {'{}A' : Coll1.ClassA, '{}B' : Coll1.ClassB})

        # With a default namespace
        disp = xmllib.NodeDispatcher({None : 'nspaceA'})
        disp.registerClasses(Coll1,Coll1.BaseType)
        self.failUnlessEqual(disp._dispatcher,
            {'{nspaceA}A' : Coll1.ClassA, '{nspaceA}B' : Coll1.ClassB})

        # One of the classes is in a different namespace
        Coll1.ClassB.tag = 'nsB:B'

        nsMap = {None : 'nspaceA', 'nsB' : 'nspaceB'}
        disp = xmllib.NodeDispatcher(nsMap = nsMap)
        disp.registerClasses(Coll1,Coll1.BaseType)
        self.failUnlessEqual(disp._dispatcher,
            {'{nspaceA}A' : Coll1.ClassA, '{nspaceB}B' : Coll1.ClassB})

        # Test that dispatching works
        n1 = xmllib.BaseNode(nsMap = nsMap, name = 'A')
        c1 = disp.dispatch(n1)
        self.failUnlessEqual(c1.__class__, Coll1.ClassA)

        n2 = xmllib.BaseNode(nsMap = nsMap, name = 'nsB:B')
        c2 = disp.dispatch(n2)
        self.failUnlessEqual(c2.__class__, Coll1.ClassB)

        # Now, an example of a class that we register directly
        class ClassC(object):
            def __init__(self, node):
                self.node = node

        disp.registerType(ClassC, name = 'C')

        n3 = xmllib.BaseNode(nsMap = nsMap, name = 'C')
        c3 = disp.dispatch(n3)
        self.failUnlessEqual(c3.__class__, ClassC)

        # And another one, now with namespace

        disp.registerType(ClassC, name = 'D', namespace = 'nsB')

        n4 = xmllib.BaseNode(nsMap = nsMap, name = 'nsB:D')
        c4 = disp.dispatch(n4)
        self.failUnlessEqual(c4.__class__, ClassC)
        self.failUnlessEqual(c4.node, n4)

        # a class we register without a name and with no getTag - should be
        # ignored
        class ClassE(object):
            def __init__(self, node):
                self.node = node

        disp.registerType(ClassE)
        self.failUnlessEqual(disp._dispatcher,
            {'{nspaceA}A' : Coll1.ClassA, '{nspaceB}B' : Coll1.ClassB,
             '{nspaceA}C' : ClassC, '{nspaceB}D' : ClassC})

        # And a node we don't handle
        n5 = xmllib.BaseNode(nsMap = nsMap, name = 'X')
        c5 = disp.dispatch(n5)
        self.failUnlessEqual(c5, None)

class SchemaValidationTest(BaseTest):
    def testGetSchemaLocationFromStream(self):
        # Exceptions first
        stream = StringIO.StringIO('No XML data')
        e = self.failUnlessRaises(xmllib.InvalidXML,
            xmllib.DataBinder.getSchemaLocationsFromStream, stream)
        self.failUnlessEqual(str(e), "Possibly malformed XML")

        stream = StringIO.StringIO('<node xmlns:xsi="what?" '
            'xsi:schemaLocation="blah1 blah2"/>')

        e = self.failUnlessRaises(xmllib.UnknownSchemaError,
            xmllib.DataBinder.getSchemaLocationsFromStream, stream)
        self.failUnlessEqual(str(e), "Schema location not specified in XML stream")

        stream = StringIO.StringIO('<node '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>')

        e = self.failUnlessRaises(xmllib.UnknownSchemaError,
            xmllib.DataBinder.getSchemaLocationsFromStream, stream)
        self.failUnlessEqual(str(e), "Schema location not specified in XML stream")

        stream = StringIO.StringIO('BAD DATA <node '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xsi:schemaLocation = "blah1 blah2"/>')
        stream.seek(9)
        self.failUnlessEqual(xmllib.DataBinder.getSchemaLocationsFromStream(stream),
            ["blah1", "blah2"])

        self.failUnlessEqual(stream.tell(), 9)

    def testChooseSchemaFile(self):
        schemaFiles = ["sf1", "sf2", "sf4", "sf5"]

        e = self.failUnlessRaises(xmllib.UnknownSchemaError,
            xmllib.DataBinder.chooseSchemaFile, schemaFiles, None)
        self.failUnlessEqual(str(e), "Schema directory not specified")

        tmpdir = tempfile.mkdtemp()

        e = self.failUnlessRaises(xmllib.UnknownSchemaError,
            xmllib.DataBinder.chooseSchemaFile, schemaFiles, tmpdir)
        self.failUnlessEqual(str(e),
            "No applicable schema found in directory `%s'" % tmpdir)

        # To make sure directory ordering doesn't matter, mock out listdir
        origListdir = os.listdir
        listdir = lambda x: ["sf4", "sf3", "sf2"]
        try:
            os.listdir = listdir
            file(os.path.join(tmpdir, "sf2"), "w")
            file(os.path.join(tmpdir, "sf3"), "w")
            file(os.path.join(tmpdir, "sf4"), "w")

            ret = xmllib.DataBinder.chooseSchemaFile(schemaFiles, tmpdir)
            self.failUnlessEqual(ret, os.path.join(tmpdir, "sf2"))
        finally:
            os.listdir = origListdir
            shutil.rmtree(tmpdir, ignore_errors = True)

        e = self.failUnlessRaises(xmllib.UnknownSchemaError,
            xmllib.DataBinder.chooseSchemaFile, schemaFiles, tmpdir)
        self.failUnlessEqual(str(e), "Schema directory `%s' not found" %
            tmpdir)

    def testClassLevelValidate(self):
        tmpdir = tempfile.mkdtemp()
        try:
            file(os.path.join(tmpdir, "schema.xsd"), "w+").write(xmlSchema1)
            stream = StringIO.StringIO(xmlData1)
            xmllib.DataBinder.validate(stream, tmpdir)

            # xmlData2 should fail
            stream = StringIO.StringIO(xmlData2)
            e = self.failUnlessRaises(xmllib.SchemaValidationError,
                xmllib.DataBinder.validate, stream, tmpdir)
            self.failUnlessEqual(str(e), schemaError2)
        finally:
            shutil.rmtree(tmpdir, ignore_errors = True)

    def testParseFileValidate(self):
        tmpdir = tempfile.mkdtemp()
        stream = StringIO.StringIO(xmlData1)
        try:
            file(os.path.join(tmpdir, "schema.xsd"), "w+").write(xmlSchema1)
            binder = xmllib.DataBinder()
            binder.parseFile(stream, validate = True, schemaDir = tmpdir)

            binder.parseString(xmlData1, validate = True, schemaDir = tmpdir)

            # Try to pass None as a schema directory - should fail
            stream.seek(0)
            e = self.failUnlessRaises(xmllib.UnknownSchemaError,
                binder.parseFile, stream, validate = True, schemaDir = None)
            self.failUnlessEqual(str(e), "Schema directory not specified")
        finally:
            shutil.rmtree(tmpdir, ignore_errors = True)

xmlSchema1 = """\
<?xml version="1.0" encoding="UTF-8"?>
<xsd:schema targetNamespace="http://my.example.com"
        elementFormDefault="qualified"
        attributeFormDefault="unqualified"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.w3.org/2001/XMLSchema.xsd"
        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
        xmlns="http://www.rpath.com/permanent/rpd-1.0.xsd">

    <xsd:element name="f">
        <xsd:complexType>
            <xsd:sequence>
                <xsd:element name="c1" type="xsd:string" />
                <xsd:element name="c2" type="xsd:string" />
            </xsd:sequence>
        </xsd:complexType>
    </xsd:element>
</xsd:schema>"""

xmlData1 = """\
<?xml version="1.0" encoding="UTF-8"?>
<f xmlns="http://my.example.com" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="schema.xsd">
  <c1/>
  <c2/>
</f>"""

xmlData2 = xmlData1.replace("<c1/>", "")

schemaError2 = (
    "<string>:4:0:ERROR:SCHEMASV:SCHEMAV_ELEMENT_CONTENT: "
    "Element '{http://my.example.com}c2': This element is not expected. "
    "Expected is ( {http://my.example.com}c1 )."
)
