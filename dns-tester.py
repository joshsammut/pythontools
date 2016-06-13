#!/usr/bin/env python

import click
import time
import dns.resolver
import dns.exception
import requests
import click
import concurrent.futures
import math

class Failure(object):
    def __init__(self, server):
        self.server = server

    def __str__(self): return self.message()

    def message(self):
        raise NotImplementedError

class WrongAddressFailure(Failure):
    def __init__(self, server, wrongAddress):
        self.wrongAddress = wrongAddress
        super(WrongAddressFailure, self).__init__(server)

    def message(self):
        return "%s - wrong address (%s)" % (self.server, self.wrongAddress)

class TTLFailure(Failure):
    def __init__(self, server, ttl):
        self.ttl = ttl
        super(TTLFailure, self).__init__(server)

    def message(self):
        return "%s - ttl too long (%s)" % (self.server, self.ttl)

class QueryTimeoutFailure(Failure):
    def message(self):
        return "%s - query timeout" % (self.server)


def check_server(server, dnsname, correct_ip, ttlmax, quiet):
    resolver = dns.resolver.Resolver()
    resolver.nameservers=[server]

    answer = None
    for i in range(0,3):
        try:
            answer = resolver.query(dnsname)
            break
        except (dns.exception.Timeout,dns.resolver.NoAnswer, dns.resolver.NoNameservers) as e:
            #timeout, keep trying
            answer = None
            time.sleep(30)
            continue

    if answer is None:
        f = QueryTimeoutFailure(server)
        if not quiet:
            print f
        return f
        
    ttl = answer.rrset.ttl

    for data in answer:
        if data.address != correct_ip:
            f = WrongAddressFailure(server, data.address)
            if not quiet:
                print f
            return f

    if ttl > ttlmax:
        f = TTLFailure(server, ttl)
        if not quiet:
            print f
        return f

    return None

@click.command()
@click.option("--dnsname", "-d", required=True, help="The hostname you are testing, ie vena.io")
@click.option("--correct-ip", "-c", required=True, help="The ip address you believe to be correct") #FIXME get this dynamically
@click.option("--ttlmax", "-t", required=True, help="The ttl set by the authoritative name server") #FIXME get this dynamically
@click.option("--sourceurl", "-s", default="http://public-dns.info/nameservers.txt", help="Url that will return a list of dns servers, separated by linebreaks, default: http://public-dns.info/nameservers.txt")
@click.option("--workers","-w", default=1000, help="The number of threads to use, default 1000") #most of the time is spent waiting for network so I've found workers of over 1000 is fine
@click.option("--quiet", "-q", is_flag=True, default=False, help="Suppress individual failures (timeout, wrong address, ttl being too high")
def main(dnsname, correct_ip, ttlmax, sourceurl, workers, quiet):
    serversRaw = requests.get(sourceurl)

    servers = serversRaw.text.split("\n")
    failed_servers = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        total = len(servers)
        print "Testing %d servers" % (total)
        futures = [ executor.submit(check_server, server, dnsname, correct_ip, ttlmax, quiet) for server in servers ]

        ttlFailures = 0
        wrongAddresses = 0
        timeouts = 0
        for i in range(0, len(futures)):
            result = futures[i].result()
            if result is not None:
                if type(result) is TTLFailure:
                    ttlFailures = ttlFailures + 1
                elif type(result) is WrongAddressFailure:
                    wrongAddresses = wrongAddresses + 1
                elif type(result) is QueryTimeoutFailure:
                    timeouts = timeouts + 1

        print "%d out of %d failed:" % (ttlFailures + wrongAddresses + timeouts, total)
        print "\t%d out of %d (%f%%) had query timeouts" % (timeouts, total, (timeouts/float(total))*100)
        print "\t%d out of %d (%f%%) had the wrong address" % (wrongAddresses, total, (wrongAddresses/float(total))*100)
        print "\t%d out of %d (%f%%) had the wrong ttl" % (ttlFailures, total, (ttlFailures/float(total))*100)

if __name__ == '__main__':
    main()
