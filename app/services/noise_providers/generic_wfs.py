class GenericWFSProvider:
    """Extension point for department/local WFS layers discovered from catalogues."""
    name="generic-wfs"
    async def query(self,client,point,errors):return {"provider":self.name,"sources":[]}
