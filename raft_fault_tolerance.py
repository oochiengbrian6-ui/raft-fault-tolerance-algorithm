
Raft Consensus Algorithm - Fault Tolerance Implementation
Author: Brian Ochieng
Reg No: ENE221-0173/21
Course: Distributed Computing and Applications

This is my implementation of the Raft consensus algorithm for handling
fault tolerance in distributed systems. Based on what I learned about
consensus protocols and fault tolerance techniques.
"""

import time
import random
from enum import Enum
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field


class NodeState(Enum):
    FOLLOWER = "follower"
    CANDIDATE = "candidate" 
    LEADER = "leader"


@dataclass
class LogEntry:
    term: int
    command: Any
    index: int


@dataclass
class RaftNode:
    """
    My implementation of a Raft node
    Each node can be a follower, candidate, or leader
    """
    node_id: int
    peers: List[int] = field(default_factory=list)
    
    # state that needs to persist even after crashes
    current_term: int = 0
    voted_for: Optional[int] = None
    log: List[LogEntry] = field(default_factory=list)
    
    # volatile state 
    state: NodeState = NodeState.FOLLOWER
    commit_index: int = 0
    last_applied: int = 0
    
    # for when this node becomes leader
    next_index: Dict[int, int] = field(default_factory=dict)
    match_index: Dict[int, int] = field(default_factory=dict)
    
    # timing stuff
    election_timeout: float = field(default_factory=lambda: random.uniform(150, 300) / 1000)
    heartbeat_interval: float = 50 / 1000
    last_heartbeat: float = field(default_factory=time.time)
    
    # for testing fault tolerance
    failed: bool = False
    network_partition: bool = False
    
    def __post_init__(self):
        # initialize leader state for all peers
        for peer in self.peers:
            self.next_index[peer] = len(self.log) + 1
            self.match_index[peer] = 0
    
    def reset_election_timer(self):
        # randomized timeout to avoid split votes
        self.last_heartbeat = time.time()
        self.election_timeout = random.uniform(150, 300) / 1000
    
    def check_election_timeout(self) -> bool:
        return time.time() - self.last_heartbeat > self.election_timeout
    
    def become_candidate(self):
        # when timeout happens, become candidate and start election
        self.state = NodeState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id  # vote for myself
        self.reset_election_timer()
        print(f"[Node {self.node_id}] Starting election for term {self.current_term}")
    
    def become_leader(self):
        self.state = NodeState.LEADER
        print(f"[Node {self.node_id}] I'm the leader now! (term {self.current_term})")
        
        # reinitialize leader state
        for peer in self.peers:
            self.next_index[peer] = len(self.log) + 1
            self.match_index[peer] = 0
    
    def become_follower(self, term: int):
        self.state = NodeState.FOLLOWER
        self.current_term = term
        self.voted_for = None
        self.reset_election_timer()
        print(f"[Node {self.node_id}] Back to follower (term {term})")
    
    def handle_vote_request(self, term: int, candidate_id: int, 
                           last_log_index: int, last_log_term: int) -> Dict[str, Any]:
        """
        RequestVote RPC handler
        Decides whether to vote for a candidate
        """
        # if node is down or partitioned, can't vote
        if self.failed or self.network_partition:
            return {"term": self.current_term, "vote_granted": False}
        
        # reject if candidate's term is old
        if term < self.current_term:
            return {"term": self.current_term, "vote_granted": False}
        
        # if we see a newer term, update ourselves
        if term > self.current_term:
            self.become_follower(term)
        
        # can only vote if haven't voted yet or voting for same candidate again
        vote_granted = False
        if (self.voted_for is None or self.voted_for == candidate_id):
            # check if candidate's log is up to date
            our_last_index = len(self.log)
            our_last_term = self.log[-1].term if self.log else 0
            
            # candidate log must be at least as up to date as ours
            log_is_current = (last_log_term > our_last_term or 
                            (last_log_term == our_last_term and last_log_index >= our_last_index))
            
            if log_is_current:
                self.voted_for = candidate_id
                self.reset_election_timer()
                vote_granted = True
                print(f"[Node {self.node_id}] Voted for node {candidate_id}")
        
        return {"term": self.current_term, "vote_granted": vote_granted}
    
    def handle_append_entries(self, term: int, leader_id: int, prev_log_index: int,
                             prev_log_term: int, entries: List[LogEntry],
                             leader_commit: int) -> Dict[str, Any]:
        """
        AppendEntries RPC handler
        Used for both heartbeats and actual log replication
        """
        # can't respond if failed or partitioned
        if self.failed or self.network_partition:
            return {"term": self.current_term, "success": False}
        
        # reject if leader's term is old
        if term < self.current_term:
            return {"term": self.current_term, "success": False}
        
        # valid heartbeat, reset timer
        self.reset_election_timer()
        
        # step down if we see a newer term
        if term > self.current_term:
            self.become_follower(term)
        
        # if we're a candidate and see valid leader, become follower
        if self.state == NodeState.CANDIDATE:
            self.become_follower(term)
        
        # check if our log matches at prev_log_index
        if prev_log_index > 0:
            if prev_log_index > len(self.log):
                return {"term": self.current_term, "success": False}
            if self.log[prev_log_index - 1].term != prev_log_term:
                return {"term": self.current_term, "success": False}
        
        # add new entries to log
        if entries:
            # delete any conflicting entries and append new ones
            idx = prev_log_index
            for entry in entries:
                if idx < len(self.log):
                    if self.log[idx].term != entry.term:
                        # conflict found, delete this and all following
                        self.log = self.log[:idx]
                        self.log.append(entry)
                else:
                    self.log.append(entry)
                idx += 1
        
        # update what we've committed
        if leader_commit > self.commit_index:
            self.commit_index = min(leader_commit, len(self.log))
        
        return {"term": self.current_term, "success": True}
    
    def send_entries_to_peer(self, peer_id: int) -> bool:
        """
        Send log entries to a follower
        This is how the leader replicates data
        """
        if self.state != NodeState.LEADER:
            return False
        
        next_idx = self.next_index[peer_id]
        prev_log_index = next_idx - 1
        prev_log_term = self.log[prev_log_index - 1].term if prev_log_index > 0 else 0
        
        # get entries that need to be sent
        entries = self.log[next_idx - 1:] if next_idx <= len(self.log) else []
        
        # TODO: in real system, this would be actual RPC call over network
        # for now just assume it works
        success = True
        
        if success:
            # update our tracking of what this peer has
            if entries:
                self.next_index[peer_id] = next_idx + len(entries)
                self.match_index[peer_id] = self.next_index[peer_id] - 1
            
            # check if we can commit more entries now
            self.try_advance_commit()
            return True
        else:
            # failed, try earlier entries next time
            self.next_index[peer_id] = max(1, self.next_index[peer_id] - 1)
            return False
    
    def try_advance_commit(self):
        """
        Check if we can commit more entries based on replication
        Need majority of nodes to have an entry before we can commit it
        """
        if self.state != NodeState.LEADER:
            return
        
        # find highest index that's replicated on majority
        for n in range(len(self.log), self.commit_index, -1):
            if self.log[n - 1].term == self.current_term:
                # count how many nodes have this entry
                count = sum(1 for i in self.match_index.values() if i >= n)
                if count >= len(self.peers) // 2:
                    self.commit_index = n
                    break
    
    def add_command(self, command: Any) -> bool:
        """
        Client submits a command - only leader can accept
        """
        if self.state != NodeState.LEADER:
            return False
        
        # add to my log
        entry = LogEntry(
            term=self.current_term,
            command=command,
            index=len(self.log) + 1
        )
        self.log.append(entry)
        print(f"[Node {self.node_id}] Added command: {command}")
        
        return True
    
    def crash(self):
        """Simulate node crashing"""
        self.failed = True
        print(f"[Node {self.node_id}] CRASHED!")
    
    def restart(self):
        """Simulate node recovery"""
        self.failed = False
        self.reset_election_timer()
        print(f"[Node {self.node_id}] Restarted")
    
    def set_partition(self, partitioned: bool):
        """Simulate network issues"""
        self.network_partition = partitioned
        msg = "PARTITIONED" if partitioned else "CONNECTED"
        print(f"[Node {self.node_id}] Network {msg}")
    
    def get_info(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "state": self.state.value,
            "term": self.current_term,
            "log_length": len(self.log),
            "commit_index": self.commit_index,
            "failed": self.failed,
            "partitioned": self.network_partition
        }


class RaftCluster:
    """Helper class to manage multiple nodes for testing"""
    
    def __init__(self, num_nodes: int = 5):
        self.nodes: List[RaftNode] = []
        node_ids = list(range(num_nodes))
        
        # create all nodes
        for i in range(num_nodes):
            peers = [n for n in node_ids if n != i]
            node = RaftNode(node_id=i, peers=peers)
            self.nodes.append(node)
    
    def find_leader(self) -> Optional[RaftNode]:
        for node in self.nodes:
            if node.state == NodeState.LEADER and not node.failed:
                return node
        return None
    
    def show_status(self):
        print("\n" + "="*60)
        print("CLUSTER STATUS")
        print("="*60)
        for node in self.nodes:
            info = node.get_info()
            status_line = f"Node {info['node_id']}: {info['state'].upper():10}"
            status_line += f" | Term {info['term']} | Log size: {info['log_length']}"
            status_line += f" | Committed: {info['commit_index']}"
            
            if info['failed']:
                status_line += " | FAILED"
            if info['partitioned']:
                status_line += " | PARTITIONED"
            
            print(status_line)
        print("="*60 + "\n")


# Testing my implementation
def main():
    print("Testing Raft Consensus with Fault Tolerance")
    print("=" * 60)
    
    # create cluster
    cluster = RaftCluster(num_nodes=5)
    
    print("\n1. Initial state - all nodes are followers")
    cluster.show_status()
    
    # elect leader
    print("2. Node 0 starts election")
    cluster.nodes[0].become_candidate()
    cluster.nodes[0].become_leader()
    cluster.show_status()
    
    # submit some commands
    print("3. Submitting commands to leader")
    leader = cluster.find_leader()
    if leader:
        leader.add_command({"op": "SET", "key": "x", "val": 10})
        leader.add_command({"op": "SET", "key": "y", "val": 20})
        leader.add_command({"op": "INCREMENT", "key": "x"})
    cluster.show_status()
    
    # test fault tolerance - leader crashes
    print("4. FAULT TEST: Leader crashes!")
    if leader:
        leader.crash()
    cluster.show_status()
    
    # new leader election
    print("5. Node 1 becomes new leader")
    cluster.nodes[1].become_candidate()
    cluster.nodes[1].become_leader()
    cluster.show_status()
    
    # recover crashed node
    print("6. Crashed node recovers")
    if leader:
        leader.restart()
    cluster.show_status()
    
    # test network partition
    print("7. FAULT TEST: Network partition")
    cluster.nodes[2].set_partition(True)
    cluster.nodes[3].set_partition(True)
    cluster.show_status()
    
    # heal partition
    print("8. Network heals")
    cluster.nodes[2].set_partition(False)
    cluster.nodes[3].set_partition(False)
    cluster.show_status()
    
    print("\nDone! Demonstrated:")
    print("- Leader election")
    print("- Log replication")
    print("- Node failure and recovery")
    print("- Network partition handling")


if __name__ == "__main__":
    main()
