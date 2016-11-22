package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._


class ConsultationTopoguideAnonyme extends Simulation {

        val httpProtocol = http
                .inferHtmlResources(C2corgConf.black_list, WhiteList())
                .acceptHeader("*/*")
                .acceptEncodingHeader("gzip, deflate")

        val scn = scenario("ConsultationTopoguideAnonyme")
                .exec(Homepage.init)
                .pause(8)
                .exec(Homepage.browse)
                .pause(6)
                .exec(Outing.view)
                .pause(14)
                .exec(Route.view)
                .pause(10)
                .exec(Waypoint.view)

        setUp(scn.inject(rampUsers(C2corgConf.num_users) over (C2corgConf.ramp_time_seconds seconds))).protocols(httpProtocol)
}
