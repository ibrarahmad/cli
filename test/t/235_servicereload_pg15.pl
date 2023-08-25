# This test case runs the command:
# ./nc service reload pg15
#

use strict;
use warnings;

use File::Which;
use IPC::Cmd qw(run);
use Try::Tiny;
use JSON;
use lib './lib';
use contains;

#
# Move into the pgedge directory.
#
 chdir("./pgedge");

#
# The next command reloads the service:

my $cmd = qq(./nc service reload pg15);
print("cmd = $cmd\n");
my ($success, $error_message, $full_buf, $stdout_buf, $stderr_buf)= IPC::Cmd::run(command => $cmd, verbose => 0);

print("full_buf = @$full_buf\n");
print("stdout_buf = @$stdout_buf\n");
print("stderr_buf = @$stderr_buf\n");

if (contains(@$stdout_buf[0], "reloading"))

{
    exit(0);
}
else
{
    exit(1);
}


