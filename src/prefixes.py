from rdflib import Namespace

LIST = 'https://w3id.org/list#'
EXPRESS = 'https://w3id.org/express#'

list = Namespace(LIST)
express = Namespace(EXPRESS)

EXPRESS_DATATYPES = {
    express.hasBoolean,
    express.hasDouble,
    express.hasHexBinary,
    express.hasInteger,
    express.hasString
}

INSTANCE = "http://linkedbuildingdata.net/ifc/resources20160725_163149/"
