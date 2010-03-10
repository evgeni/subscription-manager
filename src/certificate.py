#!/usr/bin/python
#
# Copyright (c) 2010 Red Hat, Inc.
#
# Authors: Jeff Ortel <jortel@redhat.com>
#
# This software is licensed to you under the GNU General Public License,
# version 2 (GPLv2). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv2
# along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#
# Red Hat trademarks are not licensed under GPLv2. No permission is
# granted to use or replicate Red Hat trademarks that are incorporated
# in this software or its documentation.
#

"""
Contains classes for working with x.509 certificates.
The backing implementation is M2Crypto.X509 which has insufficient
support for custom v3 extensions.  It is not intended to be a
replacement of full wrapper but instead and extension.
"""

import re
import base64
from M2Crypto import X509
from datetime import datetime as dt


class Certificate(object):
    """
    Represents and x.509 certificate.
    @ivar x509: The M2Crypto.X509 backing object.
    @type x509: L{X509}
    @ivar __ext: A dictionary of extensions L{OID}:value
    @type __ext: L{Extensions}
    """
    
    @classmethod
    def read(cls, path):
        """
        Read a certificate file.
        @param path: The path to a .pem file.
        @type path: str
        @return: A certificate
        @rtype: L{Certificate}
        """
        f = open(path)
        content = f.read()
        f.close()
        return Certificate(content)

    def __init__(self, content):
        """
        @param content: The PEM encoded content.
        @type content: str
        """
        x509 = X509.load_cert_string(content)
        self.__ext = Extensions(x509)
        self.x509 = x509
    
    def serialNumber(self):
        """
        Get the serial number
        @return: The x.509 serial number
        @rtype: str
        """
        return self.x509.get_serial_number()
    
    def subject(self):
        """
        Get the certificate subject.
        @return: A dictionary of subject fields.
        @rtype: dict
        """
        d = {}
        subject = self.x509.get_subject()
        for key, nid in subject.nid.items():
            entry = subject.get_entries_by_nid(nid)
            if len(entry):
                asn1 = entry[0].get_data()
                d[key] = str(asn1)
                continue
        return d
    
    def validRange(self):
        """
        Get the I{valid} date range.
        @return: The valid date range.
        @rtype: L{DateRange}
        """
        return DateRange(self.x509)
    
    def valid(self):
        """
        Get whether the certificate is valid based on date.
        @return: True if valid.
        @rtype: boolean
        """
        now = dt.utcnow()
        range = self.validRange()
        return ( now >= range.begin() and now <= range.end() )
    
    def extensions(self):
        """
        Get custom extensions.
        @return: An extensions object.
        @rtype: L{Extensions}
        """
        return self.__ext
            
    def __str__(self):
        return self.x509.as_text()
    
    def __cmp__(self, other):
        range = self.validRange()
        exp1 = range.end()
        range = other.validRange()
        exp2 = range.end()
        if exp1 < exp2:
            return -1
        if exp1 > exp2:
            return 1
        return 0


class Key:
    """
    The (private|public) key.
    @ivar path: The file path.
    @type path: str
    @ivar content: The PEM encoded key.
    @type content: str
    """
    
    def __init__(self, path):
        """
        @param path: The path to the .pem file.
        @type path: str
        """
        self.path = path
        self.content = self.__read()
        
    def __read(self):
        f = open(path)
        content = f.read()
        f.close()
        return content
        
    def __str__(self):
        return self.content

    
class DateRange:
    """
    Date range object converts between ASN1 and python
    datetime objects.
    @ivar x509: A certificate.
    @type x509: X509
    """
    
    ASN1_FORMAT = '%b %d %H:%M:%S %Y %Z'
    
    def __init__(self, x509):
        """
        @param x509: A certificate.
        @type x509: X509
        """
        self.x509 = x509
        
    def begin(self):
        """
        Get range beginning.
        @return: The beginning date in UTC.
        @rtype: L{datetime.datetime}
        """
        asn1 = self.x509.get_not_before()
        return dt.strptime(str(asn1), self.ASN1_FORMAT)
    
    def end(self):
        """
        Get range end.
        @return: The end date in UTC.
        @rtype: L{datetime.datetime}
        """
        asn1 = self.x509.get_not_after()
        return dt.strptime(str(asn1), self.ASN1_FORMAT)
    
    def __str__(self):
        s = []
        s.append('Begin: %s' % self.begin())
        s.append('End: %s' % self.end())
        return '\n'.join(s)


class Extensions(dict):
    """
    Represents x.509 (v3) I{custom} extensions.
    """
    
    pattern = re.compile('([0-9]+\.)+[0-9]:')
    
    def __init__(self, x509):
        """
        @param x509: A certificate object.
        @type x509: L{X509}
        """
        if isinstance(x509, dict):
            self.update(x509)
        else:
            self.__parse(x509)
        
    def ltrim(self, n):
        """
        Left trim I{n} parts.
        @param n: The number of parts to trim.
        @type n: int
        @return: The trimmed OID
        @rtype: L{Extensions}
        """
        d = {}
        for oid,v in self.items():
            d[oid.ltrim(n)] = v
        return Extensions(d)
                
    def get(self, oid):
        """
        Get the value of an extension by I{oid}.
        Note: The I{oid} may contain (*) wildcards.
        @param oid: An OID that may contain (*) wildcards.
        @type oid: str|L{OID}
        @return: The value of the first extension matched.
        @rtype: str
        """
        ext = self.find(oid, 1)
        if ext:
            return ext[0][1]
        else:
            return None
    
    def find(self, oid, limit=0):
        """
        Find all extensions matching the I{oid}.
        Note: The I{oid} may contain (*) wildcards.
        @param oid: An OID that may contain (*) wildcards.
        @type oid: str|L{OID}
        @param limit: Limit the number returned, 0=unlimited
        @type limit: int
        @return: A list of matching items.
        @rtype: (OID, value)
        @see: OID.match()
        """
        ext = []
        if isinstance(oid, str):
            oid = OID(oid)
        keyset = sorted(self.keys())
        for k in keyset:
            v = self[k]
            if k.match(oid):
                ext.append((k, v))
            if limit and len(ext) == limit:
                break
        return ext
    
    def branch(self, root):
        """
        Find a subtree by matching the oid.
        @param root: An OID that may contain (*) wildcards.
        @type root: str|L{OID}
        @return: A subtree.
        @rtype: L{Extensions}
        """
        d = {}
        if isinstance(root, str):
            root = OID(root)
        if root[-1]:
            root = root.append('')
        ln = len(root)-1
        for oid,v in self.find(root):
            trimmed = oid.ltrim(ln)
            d[trimmed] = v
        return Extensions(d)
    
    def __ext(self, x509):
        # get extensions substring
        text = x509.as_text()
        start = text.find('extensions:')
        end = text.rfind('Signature Algorithm:')
        text = text[start:end]
        return [s.strip() for s in text.split('\n')]
    
    def __parse(self, x509):
        # parse the extensions section
        oid = None
        for entry in self.__ext(x509):
            if oid is not None:
                self[oid] = entry[2:]
                oid = None
                continue
            m = self.pattern.match(entry)
            if m is None:
                continue
            oid = OID(entry[:-1])
            
    def __str__(self):
        s = []
        for item in self.items():
            s.append('%s = "%s"' % item)
        return '\n'.join(s)


class OID(object):
    """
    The Object Identifier object.
    @ivar part: The oid parts.
    @type part: [str,]
    @cvar WILDCARD: The wildcard character.
    @type WILDCARD: str
    """
    
    WILDCARD = '*'
    
    @classmethod
    def join(cls, *oid):
        return '.'.join(oid)
    
    @classmethod
    def split(cls, s):
        """
        Split an OID string.
        @param s: An OID string Eg: (1.2.3)
        @type s: str
        @return: A list of OID parts.
        @rtype: [str,]
        """
        return s.split('.')
    
    def __init__(self, oid):
        """
        @param oid: The OID value.
        @type oid: str|[str,]
        """
        if isinstance(oid, str):
            self.part = self.split(oid)
        else:
            self.part = oid
        
    def parent(self):
        """
        Get the parent OID.
        @return: The parent OID.
        @rtype: L{OID}
        """
        p = self.part[:-1]
        if p:
            return OID(p)
        
    def ltrim(self, n):
        """
        Left trim I{n} parts.
        @param n: The number of parts to trim.
        @type n: int
        @return: The trimmed OID
        @rtype: L{OID}
        """
        return OID(self.part[n:])
    
    def rtrim(self, n):
        """
        Right trim I{n} parts.
        @param n: The number of parts to trim.
        @type n: int
        @return: The trimmed OID
        @rtype: L{OID}
        """
        return OID(self.part[:-n])
    
    def append(self, oid):
        """
        Append the specified OID fragment.
        @param oid: An OID fragment.
        @type oid: str|L{OID}
        @return: The concatenated OID.
        @rtype: L{OID}
        """
        if isinstance(oid, str):
            oid = OID(oid)
        part = self.part + oid.part
        return OID(part)
        
    def match(self, oid):
        """
        Match the specified OID considering wildcards.
        Patterns:
          - 1.4.5.6.74 (not wildcarded)
          -    .5.6.74 (match on only last 4)
          -    5.6.74. (match only first 4)
          - 1.4.*.6.*  (wildcard pattern)
        @param oid: An OID string or object.
        @type oid: str|L{OID}
        @return: True if matched
        """
        i = 0
        if isinstance(oid, str):
            oid = OID(oid)
        try:
            if not oid[0]:
                oid = OID(oid[1:])
                parts = self.part[-len(oid):]
            elif not oid[-1]:
                oid = OID(oid[:-1])
                parts = self.part[:len(oid)]
            else:
                parts = self.part
            for x in parts:
                if ( x == oid[i] or oid[i] == self.WILDCARD ):
                    i += 1
                else:
                    raise Exception()
        except:
            return False
        return True
    
    def __len__(self):
        return len(self.part)
    
    def __getitem__(self, index):
        return self.part[index]
    
    def __repr__(self):
        return str(self)
    
    def __hash__(self):
        return hash(str(self))
    
    def __eq__(self, other):
        return ( str(self) == str(other) )
    
    def __str__(self):
        return '.'.join(self.part)
    

class ProductCertificate(Certificate):
    """
    Represents a Red Hat product/entitlement certificate.
    It is OID schema aware and provides methods to get
    product and entitlement information.
    @cvar REDHAT: The Red Hat base OID.
    @type REDHAT: str
    """
    
    REDHAT = '1.3.6.1.4.1.2312'
    
    @classmethod
    def read(cls, path):
        """
        Read a certificate file.
        @param path: The path to a .pem file.
        @type path: str
        @return: A certificate
        @rtype: L{Certificate}
        """
        f = open(path)
        content = f.read()
        f.close()
        return ProductCertificate(content)
    
    def __init__(self, content):
        """
        @param content: The PEM encoded content.
        @type content: str
        """
        Certificate.__init__(self, content)
        redhat = OID(self.REDHAT)
        n = len(redhat)
        self.trimmed = self.extensions().ltrim(n)

    def getProduct(self):
        """
        Get the product defined in the certificate.
        @return: A list of product object.
        @rtype: [L{Product},..]
        """
        products = self.trimmed.find('2.7.1', 1)
        if products:
            p = products[0]
            oid = p[0]
            root = oid.rtrim(1)
            ext = self.trimmed.branch(root)
            return Product(ext)
        return None
    
    def __str__(self):
        s = []
        s.append('RAW:')
        s.append('===================================')
        s.append(Certificate.__str__(self))
        s.append('MODEL:')
        s.append('===================================')
        s.append('Serial#: %s' % self.serialNumber())
        s.append('Consumer UUID: %s\n' % self.subject()['CN'])
        s.append(str(self.getProduct()))
        s.append('')
        return '\n'.join(s)
    

class EntitlementCertificate(ProductCertificate):
    """
    Represents an entitlement certificate.
    """
    
    @classmethod
    def read(cls, path):
        """
        Read a certificate file.
        @param path: The path to a .pem file.
        @type path: str
        @return: A certificate
        @rtype: L{Certificate}
        """
        f = open(path)
        content = f.read()
        f.close()
        return EntitlementCertificate(content)

    def getEntitlements(self):
        """
        Get the entitlements defined in the certificate.
        @return: A list of entitlement object.
        @rtype: [L{Entitlement},..]
        """
        lst = []
        entitlements = self.trimmed.find('3.*.1')
        for ent in entitlements:
            oid = ent[0]
            root = oid.rtrim(1)
            ext = self.trimmed.branch(root)
            lst.append(Entitlement(ext))
        return lst

    def __str__(self):
        s = []
        s.append(ProductCertificate.__str__(self))
        for ent in self.getEntitlements():
            s.append(str(ent))
        return '\n'.join(s)


class Product:

    def __init__(self, ext):
        self.ext = ext
        
    def getName(self):
        return self.ext.get('1')
    
    def getDescription(self):
        return self.ext.get('2')
    
    def getArch(self):
        return self.ext.get('3')
    
    def getVersion(self):
        return self.ext.get('4')
    
    def getQuantity(self):
        return self.ext.get('5')
    
    def getSubtype(self):
        return self.ext.get('6')
    
    def getVirtLimit(self):
        return self.ext.get('7')
    
    def getSocketLimit(self):
        return self.ext.get('8')
    
    def getProductOptionCode(self):
        return self.ext.get('9')
    
    def __eq__(self, rhs):
        return ( self.getName() == rhs.getName() )
    
    def __str__(self):
        s = []
        s.append('Product {')
        s.append('\tName ......... = %s' % self.getName())
        s.append('\tDescription .. = %s' % self.getDescription())
        s.append('\tArchitecture . = %s' % self.getArch())
        s.append('\tVersion ...... = %s' % self.getVersion())
        s.append('\tQuantity ..... = %s' % self.getQuantity())
        s.append('\tSubtype ...... = %s' % self.getSubtype())
        s.append('\tVirt Limit ... = %s' % self.getVirtLimit())
        s.append('\tSocket Limit . = %s' % self.getSocketLimit())
        s.append('\tProduct Code . = %s' % self.getProductOptionCode())
        s.append('}')
        return '\n'.join(s)

    def __repr__(self):
        return str(self)
    
    
class Entitlement:

    def __init__(self, ext):
        self.ext = ext
        
    def getName(self):
        return self.ext.get('1')
    
    def getLabel(self):
        return self.ext.get('2')
    
    def getQuantity(self):
        return self.ext.get('3')
    
    def getFlexQuantity(self):
        return self.ext.get('4')
    
    def getVendor(self):
        return self.ext.get('5')
    
    def getUrl(self):
        return self.ext.get('6')
    
    def getGpg(self):
        return self.ext.get('7')
    
    def __eq__(self, rhs):
        return ( self.getName() == rhs.getName() )
    
    def __str__(self):
        s = []
        s.append('Entitlement {')
        s.append('\tName ........ = %s' % self.getName())
        s.append('\tLabel ....... = %s' % self.getLabel())
        s.append('\tQuantity .... = %s' % self.getQuantity())
        s.append('\tFlex Quantity = %s' % self.getFlexQuantity())
        s.append('\tVendor ...... = %s' % self.getVendor())
        s.append('\tURL ......... = %s' % self.getUrl())
        s.append('\tGPG URL ..... = %s' % self.getGpg())
        s.append('}')
        return '\n'.join(s)

    def __repr__(self):
        return str(self)
    
    
class Bundle:
    
    KEY_PATTERN = re.compile(
        '(-----BEGIN.+KEY-----\n)(.+)(\n-----END.+KEY-----)',
        re.DOTALL)
    CERT_PATTERN = re.compile(
        '(-----BEGIN CERTIFICATE-----\n)(.+)(\n-----END CERTIFICATE-----)',
        re.DOTALL)
    
    @classmethod
    def split(cls, pem):
        m = cls.KEY_PATTERN.search(pem)
        key = m.group(2)
        m = cls.CERT_PATTERN.search(pem)
        cert = m.group(2)
        return Bundle(key, cert)
    
    @classmethod
    def read(cls, path):
        f = open(path)
        bundle = cls.split(f.read())
        f.close()
        return bundle
    
    def __init__(self, key, cert):
        self.key = key
        self.cert = cert
        
    def join(self):
        s = []
        s.append('-----BEGIN RSA PRIVATE KEY-----')
        s.append(self.key)
        s.append('-----END RSA PRIVATE KEY-----')
        s.append('-----BEGIN CERTIFICATE-----')
        s.append(self.cert)
        s.append('-----END CERTIFICATE-----')
        return '\n'.join(s)
        
    def write(self, path):
        f = open(path, 'w')
        f.write(self.join())
        f.close()
        return self


import sys
if __name__ == '__main__':
    for path in sys.argv[1:]:
        print path
        f = open(path)
        content = f.read()
        pc = EntitlementCertificate(content)
        print pc.x509
        print pc
