class RequestThrottle:
    def __init__(self):
        self.d = deque()
        
    def __len__(self):
        purge_date = datetime.datetime.now() - datetime.timedelta(minutes=1, seconds=5)
        while len(self.d)>0 and self.d[0]<purge_date:
            self.d.popleft()
        return len(self.d)
    
    def add(self):
        self.d.append(datetime.datetime.now())
        
    def throttle(self, verbose=False):
        while len(self)>=19:
            if verbose: print(f"length is  {len(self)} at {datetime.datetime.now()}")
            time.sleep(1)
        
        if len(self.d)==0:
            return
        
        if self.d[-1] > datetime.datetime.now() - datetime.timedelta(seconds=3):
            time.sleep(3)
