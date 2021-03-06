# -*- coding: utf-8 -*-
#
# Copyright (c), 2016-2017, SISSA (International School for Advanced Studies).
# All rights reserved.
# This file is distributed under the terms of the MIT License.
# See the file 'LICENSE' in the root directory of the present
# distribution, or http://opensource.org/licenses/MIT.
#
# @author Davide Brunato <brunato@sissa.it>
#
"""
This module contains classes for XML Schema attributes and attribute groups.
"""
from collections import MutableMapping

from ..namespaces import get_namespace, XSI_NAMESPACE_PATH
from ..exceptions import XMLSchemaAttributeError
from ..qnames import (
    get_qname, local_name, reference_to_qname, XSD_ANY_SIMPLE_TYPE, XSD_SIMPLE_TYPE_TAG,
    XSD_ATTRIBUTE_GROUP_TAG, XSD_COMPLEX_TYPE_TAG, XSD_RESTRICTION_TAG, XSD_EXTENSION_TAG,
    XSD_SEQUENCE_TAG, XSD_ALL_TAG, XSD_CHOICE_TAG, XSD_ATTRIBUTE_TAG, XSD_ANY_ATTRIBUTE_TAG
)
from .exceptions import XMLSchemaValidationError, XMLSchemaParseError
from .parseutils import check_type, get_xsd_attribute
from .xsdbase import XsdAnnotated, ValidatorMixin
from .simple_types import XsdSimpleType
from .wildcards import XsdAnyAttribute


class XsdAttribute(XsdAnnotated, ValidatorMixin):
    """
    Class for XSD 1.0 'attribute' declarations.

    <attribute
      default = string
      fixed = string
      form = (qualified | unqualified)
      id = ID
      name = NCName
      ref = QName
      type = QName
      use = (optional | prohibited | required) : optional
      {any attributes with non-schema namespace ...}>
      Content: (annotation?, simpleType?)
    </attribute>
    """
    def __init__(self, elem, schema, name=None, xsd_type=None, qualified=False, is_global=False):
        if xsd_type is not None:
            self.type = xsd_type
        self.qualified = qualified
        super(XsdAttribute, self).__init__(elem, schema, name, is_global)
        if not hasattr(self, 'type'):
            raise XMLSchemaAttributeError("undefined 'type' for %r." % self)

    def __setattr__(self, name, value):
        if name == "type":
            check_type(value, XsdSimpleType)
        super(XsdAttribute, self).__setattr__(name, value)

    def _parse(self):
        super(XsdAttribute, self)._parse()
        elem = self.elem
        self.qualified = elem.attrib.get('form', self.schema.attribute_form_default) == 'qualified'

        if self.default and self.fixed:
            self._parse_error("'default' and 'fixed' attributes are mutually exclusive")
        self._parse_properties('form', 'use')

        try:
            name = elem.attrib['name']
        except KeyError:
            # No 'name' attribute, must be a reference
            try:
                attribute_name = reference_to_qname(elem.attrib['ref'], self.namespaces)
            except KeyError:
                # Missing also the 'ref' attribute
                self.errors.append(XMLSchemaParseError(
                    "missing both 'name' and 'ref' in attribute declaration", self
                ))
                return
            else:
                xsd_attribute = self.maps.lookup_attribute(attribute_name)
                self.name = attribute_name
                self.type = xsd_attribute.type
                self.qualified = xsd_attribute.qualified
                return
        else:
            attribute_name = get_qname(self.target_namespace, name)

        xsd_type = None
        xsd_declaration = self._parse_component(elem, required=False)
        try:
            type_qname = reference_to_qname(elem.attrib['type'], self.namespaces)
        except KeyError:
            if xsd_declaration is not None:
                # No 'type' attribute in declaration, parse for child local simpleType
                xsd_type = self.BUILDERS.simple_type_factory(xsd_declaration, self.schema, xsd_type)
            else:
                # Empty declaration means xsdAnySimpleType
                xsd_type = self.maps.lookup_type(XSD_ANY_SIMPLE_TYPE)
        else:
            xsd_type = self.maps.lookup_type(type_qname)
            if xsd_declaration is not None and xsd_declaration.tag == XSD_SIMPLE_TYPE_TAG:
                raise XMLSchemaParseError("ambiguous type declaration for XSD attribute", elem=elem)
            elif xsd_declaration:
                raise XMLSchemaParseError(
                    "not allowed element in XSD attribute declaration: {}".format(xsd_declaration[0]),
                    elem=elem
                )
        self.name = attribute_name
        self.type = xsd_type

    @property
    def built(self):
        return self.type.is_global or self.type.built

    @property
    def validation_attempted(self):
        if self.built:
            return 'full'
        else:
            return self.type.validation_attempted

    @property
    def admitted_tags(self):
        return {XSD_ATTRIBUTE_TAG}

    @property
    def default(self):
        return self.elem.get('default', '')

    @property
    def fixed(self):
        return self.elem.get('fixed', '')

    @property
    def ref(self):
        return self.elem.get('ref')

    @property
    def form(self):
        return get_xsd_attribute(
            self.elem, 'form', ('qualified', 'unqualified'), default=None
        )

    @property
    def use(self):
        return get_xsd_attribute(
            self.elem, 'use', ('optional', 'prohibited', 'required'), default='optional'
        )

    def is_optional(self):
        return self.use == 'optional'

    def match(self, name):
        return self.name == name or (not self.qualified and local_name(self.name) == name)

    def iter_components(self, xsd_classes=None):
        if xsd_classes is None or isinstance(self, xsd_classes):
            yield self
        if self.ref is None and not self.type.is_global:
            for obj in self.type.iter_components(xsd_classes):
                yield obj

    def iter_decode(self, text, validation='lax', **kwargs):
        if not text and kwargs.get('use_defaults', True):
            text = self.default
        if self.fixed and text != self.fixed:
            yield XMLSchemaValidationError(self, text, "value differs from fixed value")

        for result in self.type.iter_decode(text, validation, **kwargs):
            yield result
            if not isinstance(result, XMLSchemaValidationError):
                return

    def iter_encode(self, obj, validation='lax', **kwargs):
        for result in self.type.iter_encode(obj, validation):
            yield result
            if not isinstance(result, XMLSchemaValidationError):
                return


class Xsd11Attribute(XsdAttribute):
    """
    Class for XSD 1.1 'attribute' declarations.

    <attribute
      default = string
      fixed = string
      form = (qualified | unqualified)
      id = ID
      name = NCName
      ref = QName
      targetNamespace = anyURI
      type = QName
      use = (optional | prohibited | required) : optional
      inheritable = boolean
      {any attributes with non-schema namespace . . .}>
      Content: (annotation?, simpleType?)
    </attribute>
    """
    pass


class XsdAttributeGroup(MutableMapping, XsdAnnotated):
    """
    Class for XSD 'attributeGroup' definitions.
    
    <attributeGroup
      id = ID
      name = NCName
      ref = QName
      {any attributes with non-schema namespace . . .}>
      Content: (annotation?, ((attribute | attributeGroup)*, anyAttribute?))
    </attributeGroup>
    """
    def __init__(self, elem, schema, name=None, derivation=None,
                 base_attributes=None, is_global=False):
        self.derivation = derivation
        self._attribute_group = dict()
        self.base_attributes = base_attributes
        XsdAnnotated.__init__(self, elem, schema, name, is_global)

    # Implements the abstract methods of MutableMapping
    def __getitem__(self, key):
        return self._attribute_group[key]

    def __setitem__(self, key, value):
        if key is None:
            check_type(value, XsdAnyAttribute)
        else:
            check_type(value, XsdAttribute)
        self._attribute_group[key] = value
        if key is not None and value.use == 'required':
            self.required.add(key)

    def __delitem__(self, key):
        del self._attribute_group[key]
        self.required.discard(key)

    def __iter__(self):
        if None in self._attribute_group:
            # Put AnyAttribute ('None' key) at the end of iteration
            return iter(sorted(self._attribute_group, key=lambda x: (x is None, x)))
        else:
            return iter(self._attribute_group)

    def __len__(self):
        return len(self._attribute_group)

    # Other methods
    def __setattr__(self, name, value):
        super(XsdAttributeGroup, self).__setattr__(name, value)
        if name == '_attribute_group':
            check_type(value, dict)
            for k, v in value.items():
                if k is None:
                    check_type(v, XsdAnyAttribute)
                else:
                    check_type(v, XsdAttribute)
            self.required = {
                k for k, v in self.items() if k is not None and v.use == 'required'
            }

    def _parse(self):
        super(XsdAttributeGroup, self)._parse()
        elem = self.elem
        any_attribute = False
        self.clear()
        if self.base_attributes is not None:
            self._attribute_group.update(self.base_attributes.items())

        self.name = None
        if elem.tag == XSD_ATTRIBUTE_GROUP_TAG:
            if not self.is_global:
                return  # Skip dummy definitions
            try:
                self.name = get_qname(self.target_namespace, self.elem.attrib['name'])
            except KeyError:
                self.errors.append(XMLSchemaParseError(
                    "an attribute group declaration requires a 'name' attribute.", elem=elem
                ))
                return

        for child in self._iterparse_components(elem):
            if any_attribute:
                if child.tag == XSD_ANY_ATTRIBUTE_TAG:
                    self.errors.append(XMLSchemaParseError(
                        "more anyAttribute declarations in the same attribute group:", elem=elem))
                else:
                    self.errors.append(XMLSchemaParseError(
                        "another declaration after anyAttribute:", elem=elem))
            elif child.tag == XSD_ANY_ATTRIBUTE_TAG:
                any_attribute = True
                self.update({None: XsdAnyAttribute(elem=child, schema=self.schema)})
            elif child.tag == XSD_ATTRIBUTE_TAG:
                attribute = XsdAttribute(child, self.schema)
                self[attribute.name] = attribute
            elif child.tag == XSD_ATTRIBUTE_GROUP_TAG:
                qname = reference_to_qname(get_xsd_attribute(child, 'ref'), self.namespaces)
                ref_attribute_group = self.maps.lookup_attribute_group(qname)
                self.update(ref_attribute_group.items())
            elif self.name is not None:
                self.errors.append(XMLSchemaParseError(
                    "(attribute | attributeGroup) expected, found %r:" % child, elem=elem
                ))

    @property
    def built(self):
        return all([attr.built for attr in self.values()])

    @property
    def validation_attempted(self):
        if self.built:
            return 'full'
        elif any([attr.validation_attempted == 'partial' for attr in self.values()]):
            return 'partial'
        else:
            return 'none'

    @property
    def admitted_tags(self):
        return {XSD_ATTRIBUTE_GROUP_TAG, XSD_COMPLEX_TYPE_TAG, XSD_RESTRICTION_TAG, XSD_EXTENSION_TAG,
                XSD_SEQUENCE_TAG, XSD_ALL_TAG, XSD_CHOICE_TAG, XSD_ATTRIBUTE_TAG, XSD_ANY_ATTRIBUTE_TAG}

    @property
    def ref(self):
        return self.elem.get('ref')

    def iter_components(self, xsd_classes=None):
        if xsd_classes is None or isinstance(self, xsd_classes):
            yield self
        if self.ref is None:
            for attr in self.values():
                if not attr.is_global:
                    for obj in attr.iter_components(xsd_classes):
                        yield obj

    def iter_decode(self, attrs, validation='lax', **kwargs):
        result_list = []
        required_attributes = self.required.copy()
        for name, value in attrs.items():
            qname = get_qname(self.target_namespace, name)
            try:
                xsd_attribute = self[qname]
            except KeyError:
                namespace = get_namespace(name) or self.target_namespace
                if namespace == XSI_NAMESPACE_PATH:
                    try:
                        xsd_attribute = self.maps.lookup_attribute(qname)
                    except LookupError:
                        yield XMLSchemaValidationError(
                            self, attrs, "% is not an attribute of the XSI namespace." % name
                        )
                        continue
                else:
                    try:
                        xsd_attribute = self[None]  # None key ==> anyAttribute
                        value = {qname: value}
                    except KeyError:
                        yield XMLSchemaValidationError(
                            self, attrs, "%r attribute not allowed for element." % name
                        )
                        continue
            else:
                required_attributes.discard(qname)

            for result in xsd_attribute.iter_decode(value, validation, **kwargs):
                if isinstance(result, XMLSchemaValidationError):
                    yield result
                else:
                    result_list.append((name, result))
                    break

        if required_attributes:
            yield XMLSchemaValidationError(
                self, attrs, "missing required attributes: %r" % required_attributes
            )
        yield result_list

    def iter_encode(self, attributes, validation='lax', **kwargs):
        result_list = []
        required_attributes = self.required.copy()
        try:
            attributes = attributes.items()
        except AttributeError:
            pass

        for name, value in attributes:
            qname = reference_to_qname(name, self.namespaces)
            # qname = get_qname(self.target_namespace, name)
            try:
                xsd_attribute = self[qname]
            except KeyError:
                namespace = get_namespace(name) or self.target_namespace
                if namespace == XSI_NAMESPACE_PATH:
                    try:
                        xsd_attribute = self.maps.lookup_attribute(qname)
                    except LookupError:
                        yield XMLSchemaValidationError(
                            self, attributes, "% is not an attribute of the XSI namespace." % name
                        )
                        continue
                else:
                    try:
                        xsd_attribute = self[None]  # None key ==> anyAttribute
                        value = {qname: value}
                    except KeyError:
                        yield XMLSchemaValidationError(
                            self, attributes, "%r attribute not allowed for element." % name
                        )
                        continue
            else:
                required_attributes.discard(qname)

            for result in xsd_attribute.iter_encode(value, validation, **kwargs):
                if isinstance(result, XMLSchemaValidationError):
                    yield result
                else:
                    result_list.append((name, result))
                    break

        if required_attributes:
            yield XMLSchemaValidationError(
                self, attributes, "missing required attributes %r" % required_attributes,
            )
        yield result_list
