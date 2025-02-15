import ZODB, ZODB.FileStorage, transaction
from BTrees.OOBTree import OOBTree
import persistent
import persistent.list
import transaction
import sys
import ZEO

def all_done():
    transaction.commit()
    c.close()
    db.close()
    sys.exit(0)
    storage.close()

#port = int(sys.argv[1])
storage = ZODB.FileStorage.FileStorage('/home/alienhunter/.packetserver/data.zopedb')
#db = ZEO.DB(('127.0.0.1',port))
db = ZODB.DB(storage)
c = db.open()
print("Transaction manager is 'c' variable. Call all_done() before quitting after making any changes.")

